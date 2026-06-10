"""
MiMo API smoke test — 验证能力后再改主代码
运行: cd services/python && python smoke_test_mimo.py
全部 PASS 才继续，FAIL 项看 fallback 说明
"""
import json
import os
import sys

from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MIMO_API_KEY", ""),
    base_url=os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1").replace("/chat/completions", ""),
)
MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")
results = []
strict_ok = False


# ── Test 1: 基础调用 ──────────────────────────────────────────
print("=== Test 1: 基础调用 ===")
try:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "回复数字42，不要其他内容"}],
        max_completion_tokens=10,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = resp.choices[0].message.content.strip()
    assert "42" in content, f"预期包含42，实际: {content}"
    print(f"  PASS — 返回: {content}")
    results.append(("基础调用", True, None))
except Exception as e:
    print(f"  FAIL — {e}")
    results.append(("基础调用", False, str(e)))


# ── Test 2: thinking 参数 ─────────────────────────────────────
print("=== Test 2: thinking 参数 ===")
try:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "1+1等于几？"}],
        max_completion_tokens=100,
        extra_body={"thinking": {"type": "enabled"}},
    )
    content = resp.choices[0].message.content.strip()
    # thinking 模式下可能有 reasoning_content
    reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
    print(f"  PASS — 返回: {content[:80]}")
    if reasoning:
        print(f"  reasoning_content 存在 (长度 {len(reasoning)})")
    results.append(("thinking参数", True, None))
except Exception as e:
    print(f"  FAIL — {e}")
    results.append(("thinking参数", False, str(e)))


# ── Test 3: json_object structured output ────────────────────
print("=== Test 3: json_object 输出 ===")
try:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "输出一个JSON对象，包含name(string)、score(integer)、tier(string, 只能是a/b/c之一)"},
            {"role": "user", "content": "生成一个名字叫'测试',分数88,等级b的JSON对象。只输出JSON。"},
        ],
        max_completion_tokens=100,
        extra_body={"thinking": {"type": "disabled"}},
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    parsed = json.loads(raw)
    assert isinstance(parsed, dict), f"预期 dict，实际: {type(parsed)}"
    assert parsed.get("tier") in ["a", "b", "c"], f"tier 枚举违规: {parsed}"
    print(f"  PASS — 返回: {parsed}")
    results.append(("json_object", True, None))
except Exception as e:
    print(f"  FAIL — {e}")
    results.append(("json_object", False, str(e)))


# ── Test 4: json_object + 复杂 schema ────────────────────────
print("=== Test 4: json_object 复杂嵌套 ===")
complex_prompt = """输出严格JSON，格式如下：
{
  "shots": [
    {"component": "KineticText", "text": "屏幕上的文字", "mode": "shake", "duration_frames": 45}
  ]
}
只输出JSON，不要其他文字。"""

try:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是JSON填表专员，只输出JSON。"},
            {"role": "user", "content": complex_prompt},
        ],
        max_completion_tokens=300,
        extra_body={"thinking": {"type": "disabled"}},
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    parsed = json.loads(raw)
    assert "shots" in parsed, f"缺少 shots 字段: {parsed}"
    assert isinstance(parsed["shots"], list), f"shots 不是 list: {parsed}"
    print(f"  PASS — shots 数量: {len(parsed['shots'])}")
    results.append(("json_object_complex", True, None))
except Exception as e:
    print(f"  FAIL — {e}")
    results.append(("json_object_complex", False, str(e)))


# ── 总结 ─────────────────────────────────────────────────────
print("\n=== 结果汇总 ===")
for name, ok, err in results:
    status = "PASS" if ok else "FAIL"
    print(f"  {status}  {name}" + (f"  ({err[:80]})" if err else ""))

# 写入结果供后续步骤读取
output = {
    "basic_call": results[0][1],
    "thinking": results[1][1] if len(results) > 1 else False,
    "json_object": any(r[1] for r in results if "json_object" in r[0]),
    "json_object_complex": any(r[1] for r in results if r[0] == "json_object_complex"),
}
with open("smoke_test_results.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nsmoke_test_results.json 已写入: {output}")
all_critical = output["basic_call"] and output["json_object"]
sys.exit(0 if all_critical else 1)
