"""知识验证模块 — 搜索验证 LLM 生成内容的事实准确性。

核心原则: Do No Harm — 宁漏勿错改。
- 默认保留原文。只有多来源一致 + high 置信才自动修正。
- medium 只报告不改；low 一律保留原文。
- 搜不到/冲突 → 不改，标记 unverifiable + 保留原文。
- 搜索失败 → 优雅降级，不影响主流程。

流程:
1. 从 beat content 中提取可核查的硬事实 (claims)
2. 用 DuckDuckGo 搜索验证每个声明（带重试 + 优雅降级）
3. 用 MiMo LLM 评估准确性（多来源一致检查）
4. 仅 high 置信 + 一致矛盾 → 自动修正；其余保留原文
5. 返回修正后的内容 + 验证报告（含原文 + 来源可审计）
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_API_URL = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")


# ── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass
class Claim:
    """一条可核查的事实性声明。"""
    text: str
    source_beat: str  # hook / features / payoff / grid / closing
    source_key: str   # "hook.0.text" / "features.0.items.0.title" 等


@dataclass
class ClaimVerification:
    """单条声明的验证结果。"""
    claim: Claim
    status: str  # "verified" / "corrected" / "unverifiable" / "contradicted"
    search_snippets: list[str] = field(default_factory=list)
    corrected_text: str = ""
    original_text: str = ""   # 原文，始终保留（审计用）
    reason: str = ""
    confidence: str = "medium"  # "high" / "medium" / "low"
    source_urls: list[str] = field(default_factory=list)  # 来源 URL


@dataclass
class VerifyResult:
    """验证总结果。"""
    topic: str
    total_claims: int = 0
    verified: int = 0
    corrected: int = 0
    unverifiable: int = 0
    contradictions: int = 0
    corrections: list[ClaimVerification] = field(default_factory=list)
    corrected_content: dict = field(default_factory=dict)
    skipped_claims: int = 0   # 因不适合验证而跳过的声明数


# ── Step 1: 提取可核查的硬事实 ────────────────────────────────────────────

# 需要验证的 beat key（含信息量的文本）
_FACTUAL_KEYS = {
    "hook": ["text"],
    "typewriter": ["text"],
    "payoff": ["text"],
    "features": ["items"],  # items 是数组，每个有 title/desc
    "grid": ["items"],      # items 是数组，每个有 label/description
    "closing": ["text"],
}

# 跳过的 key（纯装饰性）
_SKIP_KEYS = {"logo", "marquee"}

# ── 硬事实检测：只提取可查证的声明 ─────────────────────────────────────────

# 含数字/日期的模式
_NUMBER_PATTERN = re.compile(r'\d[\d,]*(?:\.\d+)?(?:\s*(?:年|月|日|世纪|万|亿|k|m|b|%|倍|次|个|条|种|年|岁|天|小时|分钟|秒))?')

# 主观/修辞/价值判断关键词（这些不该被验证）
_SUBJECTIVE_MARKERS = {
    "最好", "最佳", "最美", "最强", "最便宜", "最高", "最低", "第一", "唯一",
    "推荐", "首选", "必看", "必备", "必买", "必学", "惊艳", "颠覆",
    "best", "most", "top", "only", "first", "must", "essential",
    "amazing", "incredible", "perfect", "ultimate",
}


def _is_verifiable_fact(text: str) -> bool:
    """判断文本是否包含可核查的硬事实（日期/数字/专有名词）。"""
    text_lower = text.lower()

    # 排除纯主观内容
    if any(marker in text_lower for marker in _SUBJECTIVE_MARKERS):
        return False

    # 排除太短的（<5 字太模糊，无法查证）
    if len(text.strip()) < 5:
        return False

    # 排除纯标点/emoji
    if not any(c.isalnum() for c in text):
        return False

    # 有数字 → 可能是硬事实
    if _NUMBER_PATTERN.search(text):
        return True

    # 含"于/在/是/为"等判断句式 → 可能是事实
    if re.search(r'[一-鿿](?:于|在|是|为|有|共|占|达|创|获|发布|推出|成立于|建立于|开始于|结束于)', text):
        return True

    return False


def extract_claims(content: dict) -> list[Claim]:
    """从 beat content 中提取可核查的硬事实声明。

    只提取含数字/日期/专有名词的事实性声明，跳过主观内容。
    """
    claims = []

    for beat_id, beat_data in content.items():
        if beat_id in _SKIP_KEYS or not isinstance(beat_data, dict):
            continue

        for comp_idx, comp_data in beat_data.items():
            if not isinstance(comp_data, dict):
                continue

            for key, value in comp_data.items():
                if key == "text" and isinstance(value, str) and len(value) > 3:
                    if _is_verifiable_fact(value):
                        claims.append(Claim(
                            text=value,
                            source_beat=beat_id,
                            source_key=f"{beat_id}.{comp_idx}.text",
                        ))
                elif key == "items" and isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            for item_key in ["title", "desc", "description", "label"]:
                                item_val = item.get(item_key, "")
                                if isinstance(item_val, str) and len(item_val) > 3:
                                    if _is_verifiable_fact(item_val):
                                        claims.append(Claim(
                                            text=item_val,
                                            source_beat=beat_id,
                                            source_key=f"{beat_id}.{comp_idx}.items.{i}.{item_key}",
                                        ))

    return claims


# ── Step 2: Web 搜索（带重试 + 优雅降级）──────────────────────────────────

def search_web(query: str, max_results: int = 3, retries: int = 2) -> list[str]:
    """用 DuckDuckGo 搜索，返回 snippet 列表。

    带重试 + 优雅降级：搜索失败返回空列表，不影响主流程。
    """
    for attempt in range(retries + 1):
        try:
            from ddgs import DDGS
            results = DDGS().text(query, max_results=max_results)
            snippets = []
            for r in results:
                body = r.get("body", "")
                if body:
                    snippets.append(body[:300])
            return snippets
        except Exception as e:
            if attempt < retries:
                wait = 1.0 * (attempt + 1)  # 1s, 2s
                logger.info(f"搜索重试 ({attempt+1}/{retries}): {e}, 等待 {wait}s")
                time.sleep(wait)
            else:
                logger.warning(f"搜索失败（已重试 {retries} 次）: {e}")
                return []


def build_search_queries(claim_text: str, topic: str) -> list[str]:
    """为声明构建搜索查询（中英文各一条）。"""
    queries = []
    # 中文查询
    q_cn = claim_text[:50]
    if topic:
        q_cn = f"{topic} {q_cn}"
    queries.append(q_cn)

    # 英文查询（提取数字和关键词）
    numbers = re.findall(r'[\d,]+(?:\.\d+)?', claim_text)
    if numbers:
        q_en = f"{topic} {numbers[0]}" if topic else numbers[0]
        queries.append(q_en)

    return queries


# ── Step 3: 多来源一致检查 ──────────────────────────────────────────────

def _multi_source_agreement(
    claim_text: str,
    search_results: list[str],
) -> str:
    """检查多个搜索结果是否一致支持或矛盾该声明。

    返回:
        "consistent_supports"  — 多数结果支持声明
        "consistent_contradicts" — 多数结果矛盾声明
        "mixed" / "no_evidence" — 证据混合或无证据
    """
    if not search_results:
        return "no_evidence"

    # 简单关键词重叠检查：声明中的关键数字/词是否出现在搜索结果中
    # 提取声明中的数字
    claim_numbers = set(re.findall(r'\d[\d,]*(?:\.\d+)?', claim_text))

    supports = 0
    contradicts = 0

    for snippet in search_results:
        snippet_lower = snippet.lower()
        # 检查声明中的数字是否出现在 snippet 中
        found_numbers = set(re.findall(r'\d[\d,]*(?:\.\d+)?', snippet))

        if claim_numbers and claim_numbers.issubset(found_numbers):
            supports += 1
        elif claim_numbers and not claim_numbers.intersection(found_numbers):
            # 数字不匹配 → 可能矛盾
            contradicts += 1
        else:
            # 无明确证据
            pass

    total = len(search_results)
    if supports >= 2 and supports > contradicts:
        return "consistent_supports"
    elif contradicts >= 2 and contradicts > supports:
        return "consistent_contradicts"
    elif supports > 0 or contradicts > 0:
        return "mixed"
    else:
        return "no_evidence"


# ── Step 3b: LLM 评估（批处理 + 多来源一致）──────────────────────────────

def verify_with_llm(
    claims: list[Claim],
    search_results: dict[str, list[str]],
    topic: str,
) -> list[ClaimVerification]:
    """用 MiMo LLM 评估声明的准确性（批处理，一次调用）。

    关键改进:
    - 批处理: 所有声明一次 LLM 调用
    - 多来源一致: 在 prompt 中注入一致检查结果
    - 保守策略: prompt 中强调"只有确信才判 corrected/contradicted"
    """
    if not MIMO_API_KEY:
        logger.warning("MIMO_API_KEY 未设置，跳过 LLM 验证")
        return [ClaimVerification(
            claim=c, status="unverifiable",
            original_text=c.text,
            reason="MIMO_API_KEY 未设置",
        ) for c in claims]

    # 构造 prompt（含多来源一致信息）
    claim_entries = []
    for i, c in enumerate(claims):
        snippets = search_results.get(c.text, [])
        # 多来源一致检查
        agreement = _multi_source_agreement(c.text, snippets)

        snippet_text = "\n".join(f"  - {s}" for s in snippets[:3]) if snippets else "  (无搜索结果)"
        claim_entries.append(
            f"声明 {i+1}: \"{c.text}\"\n"
            f"搜索结果:\n{snippet_text}\n"
            f"多来源一致检查: {agreement}"
        )

    claims_text = "\n\n".join(claim_entries)

    system_prompt = (
        f"你是事实核查专家。主题: {topic}\n"
        f"下方是 LLM 生成的短视频内容中的事实性声明，以及对应的搜索结果。\n"
        f"请逐条判断每个声明的准确性。\n\n"
        f"核心原则 — Do No Harm（宁漏勿错改）:\n"
        f"- 默认信任原文。只有当搜索结果强、多来源一致矛盾时才判 corrected/contradicted。\n"
        f"- 证据弱 / 冲突 / 搜不到 → 判 unverifiable，不要改。\n"
        f"- confidence 只在 100% 确定时才给 high。\n"
        f"- 如果不确定，宁可放过，不要误改。\n\n"
        f"规则:\n"
        f"- 如果搜索结果明确支持声明 → status=verified\n"
        f"- 如果搜索结果明确矛盾声明，且多来源一致 → status=contradicted，给出 corrected_text\n"
        f"- 如果搜索结果不包含相关信息 → status=unverifiable\n"
        f"- 如果声明有小错误（如年份差1年）且确信 → status=corrected，给出 corrected_text\n"
        f"- 如果证据不充分或冲突 → status=unverifiable（保留原文）\n\n"
        f"输出 JSON 格式:\n"
        f'{{\n'
        f'  "verifications": [\n'
        f'    {{"index": 1, "status": "verified|corrected|unverifiable|contradicted", '
        f'"corrected_text": "...", "reason": "...", "confidence": "high|medium|low"}}\n'
        f'  ]\n'
        f'}}\n'
        f"只输出 JSON，不要其他文字。"
    )

    user_content = f"主题: {topic}\n\n{claims_text}"

    try:
        resp = httpx.post(
            MIMO_API_URL,
            json={
                "model": MIMO_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.1,
                "max_tokens": 2000,
            },
            headers={"Authorization": f"Bearer {MIMO_API_KEY}"},
            timeout=120.0,
        )
        if resp.status_code != 200:
            logger.warning(f"LLM 验证调用失败: {resp.status_code}")
            return [ClaimVerification(
                claim=c, status="unverifiable",
                original_text=c.text,
                reason=f"LLM 调用失败: HTTP {resp.status_code}",
            ) for c in claims]

        msg = resp.json()["choices"][0]["message"]
        text = msg.get("content", "").strip()
        if not text:
            text = msg.get("reasoning_content", "").strip()

        # 解析 JSON
        match = re.search(r'\{[\s\S]*\}', text)
        if not match:
            logger.warning(f"LLM 输出无法解析: {text[:200]}")
            return [ClaimVerification(
                claim=c, status="unverifiable",
                original_text=c.text,
                reason="LLM 输出格式错误",
            ) for c in claims]

        data = json.loads(match.group())
        verifications = data.get("verifications", [])

        results = []
        for i, c in enumerate(claims):
            v = verifications[i] if i < len(verifications) else {}
            results.append(ClaimVerification(
                claim=c,
                status=v.get("status", "unverifiable"),
                search_snippets=search_results.get(c.text, []),
                corrected_text=v.get("corrected_text", ""),
                original_text=c.text,
                reason=v.get("reason", ""),
                confidence=v.get("confidence", "medium"),
            ))
        return results

    except Exception as e:
        logger.warning(f"LLM 验证异常: {e}")
        return [ClaimVerification(
            claim=c, status="unverifiable",
            original_text=c.text,
            reason=f"LLM 异常: {e}",
        ) for c in claims]


# ── Step 4: 应用修正（Do No Harm 护栏）─────────────────────────────────

def apply_corrections(content: dict, verifications: list[ClaimVerification]) -> dict:
    """将修正后的内容写回 beat content。

    Do No Harm 护栏:
    - 只有 confidence=high 且 status=corrected/contradicted 才自动应用。
    - confidence=medium → 只报告，不改。
    - confidence=low → 一律保留原文。
    """
    corrected = copy.deepcopy(content)

    for v in verifications:
        # ── 护栏: 只有 high 置信才自动改 ──
        if v.confidence != "high":
            continue
        if v.status not in ("corrected", "contradicted"):
            continue
        if not v.corrected_text:
            continue

        # 按 source_key 定位并替换
        parts = v.claim.source_key.split(".")
        try:
            if len(parts) == 3:  # beat_id.comp_idx.text
                beat_id, comp_idx, key = parts
                corrected[beat_id][comp_idx][key] = v.corrected_text
            elif len(parts) == 5:  # beat_id.comp_idx.items.item_idx.item_key
                beat_id, comp_idx, _, item_idx, item_key = parts
                corrected[beat_id][comp_idx]["items"][int(item_idx)][item_key] = v.corrected_text
        except (KeyError, IndexError) as e:
            logger.warning(f"应用修正失败 ({v.claim.source_key}): {e}")

    return corrected


# ── 主入口 ────────────────────────────────────────────────────────────────

def verify_knowledge(topic: str, content: dict, parallel: bool = True) -> VerifyResult:
    """验证 beat content 中的事实准确性。

    Do No Harm 原则:
    - 默认保留原文
    - 只有多来源一致 + high 置信才自动修正
    - 搜索失败优雅降级，不影响主流程

    Args:
        topic: 视频主题
        content: LLM 生成的 beat content (hook/typewriter/features/payoff/grid/closing/logo)
        parallel: 是否并行搜索（默认 True）

    Returns:
        VerifyResult: 包含修正后的内容和验证报告
    """
    result = VerifyResult(topic=topic)

    # Step 1: 提取声明（只提取可核查的硬事实）
    claims = extract_claims(content)
    result.total_claims = len(claims)

    if not claims:
        result.corrected_content = content
        return result

    logger.info(f"知识验证: 提取 {len(claims)} 条可核查声明, 主题={topic}")

    # Step 2: 搜索验证（可并行）
    search_results: dict[str, list[str]] = {}

    def _search_claim(claim: Claim) -> tuple[str, list[str]]:
        queries = build_search_queries(claim.text, topic)
        all_snippets = []
        for q in queries:
            snippets = search_web(q)
            all_snippets.extend(snippets)
        return claim.text, all_snippets

    if parallel:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_search_claim, c): c for c in claims}
            for future in as_completed(futures):
                try:
                    text, snippets = future.result()
                    search_results[text] = snippets
                except Exception as e:
                    c = futures[future]
                    logger.warning(f"搜索异常 ({c.text[:30]}): {e}")
                    search_results[c.text] = []
    else:
        for claim in claims:
            text, snippets = _search_claim(claim)
            search_results[text] = snippets

    # Step 3: LLM 评估（含多来源一致检查）
    verifications = verify_with_llm(claims, search_results, topic)

    # 统计
    for v in verifications:
        if v.status == "verified":
            result.verified += 1
        elif v.status in ("corrected", "contradicted"):
            if v.confidence == "high":
                result.corrected += 1
                result.corrections.append(v)
            else:
                # medium/low → 只报告不改，算入 unverifiable
                result.unverifiable += 1
                logger.info(
                    f"  保留原文 (confidence={v.confidence}): {v.claim.text[:30]}... "
                    f"→ {v.status} 但不自动修正"
                )
        else:
            result.unverifiable += 1

    logger.info(
        f"知识验证完成: verified={result.verified}, corrected={result.corrected}, "
        f"unverifiable={result.unverifiable} (含 medium/low 不自动修正)"
    )

    # Step 4: 应用修正（Do No Harm：只有 high 置信才改）
    result.corrected_content = apply_corrections(content, verifications)

    return result
