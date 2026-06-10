/**
 * Remotion render script: reads material_assignment.json → renders mp4.
 *
 * Usage: npx tsx scripts/render.ts <assignment-json-path> <output-mp4-path>
 *
 * Steps:
 * 1. Read material_assignment.json
 * 2. Copy materials to web/public/materials/ (for staticFile)
 * 3. Transform paths → filenames in assignment data
 * 4. Call Remotion CLI to render ViralVideo composition
 */

import { execSync } from "child_process";
import { readFileSync, writeFileSync, copyFileSync, mkdirSync, existsSync } from "fs";
import { basename, dirname, resolve } from "path";

const assignmentPath = process.argv[2];
const outputPath = process.argv[3];
const durationOverride = process.argv[4] ? Number(process.argv[4]) : 0;

if (!assignmentPath || !outputPath) {
  console.error("Usage: npx tsx scripts/render.ts <assignment.json> <output.mp4> [duration_seconds]");
  process.exit(1);
}

// Read assignment
const assignment = JSON.parse(readFileSync(resolve(assignmentPath), "utf-8"));

// Setup public/materials dir
const publicMaterialsDir = resolve("web/public/materials");
mkdirSync(publicMaterialsDir, { recursive: true });

// Copy materials and transform paths → filenames
for (const phase of assignment.phases) {
  for (const mat of phase.materials) {
    const srcPath = resolve(mat.path);
    const filename = basename(mat.path);
    const destPath = resolve(publicMaterialsDir, filename);
    if (existsSync(srcPath) && !existsSync(destPath)) {
      copyFileSync(srcPath, destPath);
    }
    mat.filename = filename;
    delete mat.path;
  }
}

// Write transformed assignment to temp file for props
const tmpPropsPath = resolve("tmp/render_props.json");
mkdirSync(dirname(tmpPropsPath), { recursive: true });
writeFileSync(tmpPropsPath, JSON.stringify({ assignment }), "utf-8");

// Calculate total frames
const fps = 30;
let totalDurationS = 0;
for (const phase of assignment.phases) {
  totalDurationS += Math.max(phase.total_duration_s, 1);
}
// Use override if provided, otherwise clamp to 15-30s
if (durationOverride > 0) {
  totalDurationS = Math.max(10, Math.min(45, durationOverride));
} else {
  totalDurationS = Math.max(15, Math.min(30, totalDurationS));
}
const totalFrames = Math.round(totalDurationS * fps);

console.log(`Rendering ${assignment.phases.length} phases, ${totalDurationS}s (${totalFrames} frames @ ${fps}fps)`);

// Ensure output directory exists
mkdirSync(dirname(resolve(outputPath)), { recursive: true });

// Render with Remotion CLI
const compId = "ViralVideo";
const propsJson = readFileSync(tmpPropsPath, "utf-8");
const webDir = resolve("web");
const entryPoint = resolve(webDir, "src/remotion/index.ts");
const absOutputPath = resolve(outputPath);

const cmd = [
  "npx remotion render",
  entryPoint,
  compId,
  absOutputPath,
  `--props='${propsJson}'`,
  `--fps=${fps}`,
  "--width=1080",
  "--height=1920",
  `--duration-in-frames=${totalFrames}`,
  "--codec=h264",
].join(" ");

console.log(`Running: ${cmd}`);

try {
  execSync(cmd, {
    stdio: "inherit",
    cwd: webDir,
    env: { ...process.env },
  });
  console.log(`\n✅ Rendered to ${resolve(outputPath)}`);
} catch (err) {
  console.error("❌ Render failed:", err);
  process.exit(1);
}
