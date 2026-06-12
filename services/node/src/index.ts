import express from 'express';
import cors from 'cors';
import axios from 'axios';
import { execFileSync } from 'child_process';
import { resolve } from 'path';
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'fs';
import { randomBytes } from 'crypto';

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_URL = process.env.PYTHON_URL || 'http://localhost:8000';
const PROJECT_ROOT = resolve(__dirname, '../../..');

// ─── 统一超时配置 ──────────────────────────────────────────────────────────
// SAM2 + VLM + Gemini 管线很长，所有代理到 Python 的请求都用 axios + 长超时
const AXIOS_TIMEOUT = 600_000; // 10 min
const RENDER_TIMEOUT = 600_000; // 10 min (Remotion 渲染)

/** 向 Python 发 POST 请求，统一超时和错误处理 */
async function pyPost(path: string, data: Record<string, unknown>) {
  const resp = await axios.post(`${PYTHON_URL}${path}`, data, {
    timeout: AXIOS_TIMEOUT,
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
  });
  return resp.data;
}

/** 向 Python 发 GET 请求 */
async function pyGet(path: string) {
  const resp = await axios.get(`${PYTHON_URL}${path}`, { timeout: AXIOS_TIMEOUT });
  return resp.data;
}

app.use(cors());
app.use(express.json({ limit: '500mb' }));

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'vst-node-orchestrator' });
});

// ─── Upload endpoint ────────────────────────────────────────────────────────

interface UploadBody {
  video?: { name: string; data: string }; // base64 (single, backward compatible)
  videos?: { name: string; data: string }[]; // base64 (multiple)
  materials: { name: string; data: string }[]; // base64
}

app.post('/api/upload', (req, res) => {
  const { video, videos, materials } = req.body as UploadBody;

  // Accept either single `video` or `videos` array
  const videoList: { name: string; data: string }[] = [];
  if (videos && videos.length > 0) {
    videoList.push(...videos);
  } else if (video?.data && video?.name) {
    videoList.push(video);
  }

  if (videoList.length === 0) {
    return res.status(400).json({ error: 'At least one video is required (use `video` or `videos`)' });
  }

  const jobId = randomBytes(4).toString('hex');
  const jobDir = resolve(PROJECT_ROOT, 'data/uploads', jobId);
  const videoDir = resolve(jobDir, 'video');
  const materialDir = resolve(jobDir, 'materials');
  mkdirSync(videoDir, { recursive: true });
  mkdirSync(materialDir, { recursive: true });

  // Save all videos
  const videoPaths: string[] = [];
  for (const v of videoList) {
    const videoPath = resolve(videoDir, v.name);
    writeFileSync(videoPath, Buffer.from(v.data, 'base64'));
    videoPaths.push(videoPath);
  }

  // Save materials
  const materialPaths: string[] = [];
  for (const mat of materials || []) {
    const matPath = resolve(materialDir, mat.name);
    writeFileSync(matPath, Buffer.from(mat.data, 'base64'));
    materialPaths.push(matPath);
  }

  return res.json({
    success: true,
    jobId,
    videoPath: videoPaths[0], // backward compatible
    videoPaths,
    materialDir,
    materialPaths,
  });
});

// ─── Pipeline endpoints ─────────────────────────────────────────────────────

interface ExtractBody {
  videoPath?: string;
  videoPaths?: string[];
}

interface GapBody {
  structureTemplate: Record<string, unknown>;
  materialDir: string;
}

interface AssignBody {
  gapReportPath: string;
  templatePath: string;
  materialDir: string;
}

interface RenderBody {
  assignmentPath: string;
  outputName?: string;
}

app.post('/api/extract', async (req, res) => {
  const { videoPath, videoPaths } = req.body as ExtractBody;

  const paths = videoPaths || (videoPath ? [videoPath] : []);
  if (paths.length === 0) {
    return res.status(400).json({ error: 'videoPath or videoPaths is required' });
  }

  try {
    const data = await pyPost('/extract', { video_path: paths[0], video_paths: paths });
    return res.json({
      success: true,
      templateId: data.template_id,
      shots: data.shots,
      structureTemplate: data.structure_template,
      outputDir: data.output_dir,
      templatePath: `${data.output_dir}/structure_template.json`,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

app.post('/api/gap', async (req, res) => {
  const { structureTemplate, materialDir } = req.body as GapBody;

  if (!structureTemplate || !materialDir) {
    return res.status(400).json({ error: 'structureTemplate and materialDir are required' });
  }

  try {
    const data = await pyPost('/gap', {
      structure_template: structureTemplate,
      material_dir: materialDir,
    });
    return res.json({
      success: true,
      gapReport: data.gap_report,
      outputDir: data.output_dir,
      gapReportPath: `${data.output_dir}/gap_report.json`,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

app.post('/api/assign', async (req, res) => {
  const { gapReportPath, templatePath, materialDir } = req.body as AssignBody;

  if (!gapReportPath || !templatePath || !materialDir) {
    return res.status(400).json({ error: 'gapReportPath, templatePath, and materialDir are required' });
  }

  try {
    const data = await pyPost('/assign', {
      gap_report_path: gapReportPath,
      template_path: templatePath,
      material_dir: materialDir,
    });
    return res.json({
      success: true,
      assignment: data.assignment,
      outputDir: data.output_dir,
      assignmentPath: `${data.output_dir}/material_assignment.json`,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

interface RenderVariant {
  mode: string;
  duration: number;
  videoData: string;
  outputPath: string;
  videoSize: number;
}

app.post('/api/render', async (req, res) => {
  const { assignmentPath } = req.body as RenderBody;

  if (!assignmentPath) {
    return res.status(400).json({ error: 'assignmentPath is required' });
  }

  const jobId = randomBytes(4).toString('hex');
  const outputDir = resolve(PROJECT_ROOT, 'data/output', `render_${jobId}`);
  mkdirSync(outputDir, { recursive: true });

  // 3 variants: compact (15s), standard (22s), relaxed (30s)
  const variants = [
    { mode: 'compact', duration: 15, filename: 'compact.mp4' },
    { mode: 'standard', duration: 22, filename: 'standard.mp4' },
    { mode: 'relaxed', duration: 30, filename: 'relaxed.mp4' },
  ];

  try {
    const scriptPath = resolve(PROJECT_ROOT, 'scripts/render.ts');
    const results: RenderVariant[] = [];

    for (const v of variants) {
      const outputFile = resolve(outputDir, v.filename);
      console.log(`Rendering ${v.mode} (${v.duration}s)`);
      execFileSync('npx', ['tsx', scriptPath, assignmentPath, outputFile, String(v.duration)], {
        stdio: 'pipe',
        cwd: PROJECT_ROOT,
        timeout: RENDER_TIMEOUT,
      });

      const videoBuffer = readFileSync(outputFile);
      results.push({
        mode: v.mode,
        duration: v.duration,
        videoData: videoBuffer.toString('base64'),
        outputPath: outputFile,
        videoSize: videoBuffer.length,
      });
    }

    return res.json({
      success: true,
      jobId,
      variants: results,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(500).json({ error: `Render failed: ${message}` });
  }
});

// ─── ScriptDrivenVideo render (for NL Scene Editor) ─────────────────────────

app.post('/api/render_script', async (req, res) => {
  const { specPath } = req.body as { specPath: string };

  if (!specPath) {
    return res.status(400).json({ error: 'specPath is required' });
  }

  const absSpecPath = resolve(PROJECT_ROOT, specPath);
  if (!existsSync(absSpecPath)) {
    return res.status(400).json({ error: `Spec file not found: ${specPath}` });
  }

  const jobId = randomBytes(4).toString('hex');
  const outputDir = resolve(PROJECT_ROOT, 'data/output', `script_${jobId}`);
  mkdirSync(outputDir, { recursive: true });
  const outputFile = resolve(outputDir, 'output.mp4');

  try {
    const scriptPath = resolve(PROJECT_ROOT, 'scripts/render_script.ts');
    console.log(`Rendering ScriptDrivenVideo from ${specPath}`);
    execFileSync('npx', ['tsx', scriptPath, absSpecPath, outputFile], {
      stdio: 'pipe',
      cwd: PROJECT_ROOT,
      timeout: RENDER_TIMEOUT,
    });

    const videoBuffer = readFileSync(outputFile);
    return res.json({
      success: true,
      jobId,
      videoData: videoBuffer.toString('base64'),
      outputPath: outputFile,
      videoSize: videoBuffer.length,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(500).json({ error: `Script render failed: ${message}` });
  }
});

// ─── Serve output files ─────────────────────────────────────────────────────

// ─── Style Migration endpoint ──────────────────────────────────────────────

app.post('/api/render_scene', async (req, res) => {
  const { composition, props, width, height, durationInFrames } = req.body as {
    composition: string;
    props: Record<string, unknown>;
    width: number;
    height: number;
    durationInFrames: number;
  };

  if (!composition || !props) {
    return res.status(400).json({ error: 'composition and props are required' });
  }

  const jobId = randomBytes(4).toString('hex');
  const outputDir = resolve(PROJECT_ROOT, 'data/output', `render_${jobId}`);
  mkdirSync(outputDir, { recursive: true });

  const outputFile = resolve(outputDir, 'output.mp4');
  const propsFile = resolve(outputDir, 'props.json');
  writeFileSync(propsFile, JSON.stringify(props));

  try {
    const entryPoint = resolve(PROJECT_ROOT, 'web/src/remotion/index.ts');
    const w = width || 1280;
    const h = height || 720;
    const dur = durationInFrames || 900;

    console.log(`Rendering ${composition}: ${w}x${h}, ${dur}f`);
    execFileSync('npx', [
      'remotion', 'render',
      entryPoint, composition, outputFile,
      `--props=${propsFile}`,
      '--fps=30',
      `--width=${w}`,
      `--height=${h}`,
      `--duration-in-frames=${dur}`,
      '--codec=h264',
      '--timeout=120000',
    ], {
      stdio: 'pipe',
      cwd: resolve(PROJECT_ROOT, 'web'),
      timeout: 600000,
    });

    const videoBuffer = readFileSync(outputFile);
    return res.json({
      success: true,
      videoData: videoBuffer.toString('base64'),
      outputPath: outputFile,
      videoSize: videoBuffer.length,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error('Render error:', message);
    return res.status(500).json({ error: `Render failed: ${message}` });
  }
});

app.post('/api/style_migrate', async (req, res) => {
  const { videoPath, topic } = req.body as { videoPath: string; topic: string };

  if (!videoPath || !topic) {
    return res.status(400).json({ error: 'videoPath and topic are required' });
  }

  try {
    // style_migrate 需要 15-20 分钟（SAM2 + VLM + Gemini），单独设 30 分钟超时
    const resp = await axios.post(`${PYTHON_URL}/style_migrate`, { video_path: videoPath, topic }, {
      timeout: 2_400_000, // 40 min — SAM2 + VLM + Gemini 管线需要 30+ 分钟
      maxBodyLength: Infinity,
      maxContentLength: Infinity,
    });
    return res.json(resp.data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

app.get('/output/:jobDir/:filename', (req, res) => {
  const { jobDir, filename } = req.params;
  const filePath = resolve(PROJECT_ROOT, 'data/output', jobDir, filename);
  if (!existsSync(filePath)) {
    return res.status(404).json({ error: 'File not found' });
  }
  res.sendFile(filePath);
});

app.listen(PORT, () => {
  console.log(`Node orchestrator running on http://localhost:${PORT}`);
});


// ─── Knowledge Base endpoints ────────────────────────────────────────────────

interface KBRecommendBody {
  shotTypes: string[];
  phase: string;
}

app.get('/api/kb/patterns', async (_req, res) => {
  try {
    const data = await pyGet('/kb/patterns');
    return res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

app.get('/api/kb/subgraph/:patternId', async (req, res) => {
  const { patternId } = req.params;
  try {
    const data = await pyGet(`/kb/subgraph/${patternId}`);
    return res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

interface UpdateAssignBody {
  assignmentPath: string;
  overrides: { phase: string; strategyId?: string; materialPaths?: string[] }[];
  templatePath: string;
  materialDir: string;
}

app.post('/api/assign/update', async (req, res) => {
  const { assignmentPath, overrides, templatePath, materialDir } = req.body as UpdateAssignBody;

  if (!assignmentPath || !templatePath || !materialDir) {
    return res.status(400).json({ error: 'assignmentPath, templatePath, and materialDir are required' });
  }

  try {
    const data = await pyPost('/assign/update', {
      assignment_path: assignmentPath,
      overrides: overrides.map(o => ({
        phase: o.phase,
        strategy_id: o.strategyId || null,
        material_paths: o.materialPaths || null,
      })),
      template_path: templatePath,
      material_dir: materialDir,
    });
    return res.json({
      success: true,
      assignment: data.assignment,
      outputDir: data.output_dir,
      assignmentPath: `${data.output_dir}/material_assignment.json`,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

interface KBIngestBody {
  template: Record<string, unknown>;
  vertical?: string;
}

app.post('/api/kb/ingest', async (req, res) => {
  const { template, vertical } = req.body as KBIngestBody;

  if (!template) {
    return res.status(400).json({ error: 'template is required' });
  }

  try {
    const data = await pyPost('/kb/ingest', { template, vertical: vertical || '通用' });
    return res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

app.post('/api/kb/recommend', async (req, res) => {
  const { shotTypes, phase } = req.body as KBRecommendBody;

  if (!shotTypes?.length || !phase) {
    return res.status(400).json({ error: 'shotTypes and phase are required' });
  }

  try {
    const data = await pyPost('/kb/recommend', { shot_types: shotTypes, phase });
    return res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

// ─── NL Scene Editor ─────────────────────────────────────────────────────────

interface SceneEditBody {
  specPath: string;
  instruction: string;
}

app.post('/api/edit/scene', async (req, res) => {
  const { specPath, instruction } = req.body as SceneEditBody;

  if (!specPath || !instruction) {
    return res.status(400).json({ error: 'specPath and instruction are required' });
  }

  try {
    const data = await pyPost('/edit/scene', { spec_path: specPath, instruction });
    return res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

// ─── Orchestrate proxy ──────────────────────────────────────────────────────

app.post('/api/orchestrate', async (req, res) => {
  try {
    const data = await pyPost('/orchestrate', req.body);
    return res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});

// ─── NL Edit proxy ──────────────────────────────────────────────────────────

app.post('/api/edit/nl', async (req, res) => {
  try {
    const data = await pyPost('/edit/nl', req.body);
    return res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return res.status(502).json({ error: `Failed to reach Python service: ${message}` });
  }
});
