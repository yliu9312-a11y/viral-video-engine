/**
 * Render a ScriptDrivenVideo composition from an animation script JSON.
 *
 * Usage: npx tsx scripts/render_script.ts <script.json> <output.mp4> [totalFrames]
 */

import { execFileSync } from "child_process";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { basename, dirname, resolve } from "path";

const scriptPath = process.argv[2];
const outputPath = process.argv[3];

if (!scriptPath || !outputPath) {
  console.error("Usage: npx tsx scripts/render_script.ts <script.json> <output.mp4> [totalFrames]");
  process.exit(1);
}

// Read script
const script = JSON.parse(readFileSync(resolve(scriptPath), "utf-8"));

// Calculate duration from shots (auto-detect, CLI arg overrides)
let totalFrames = 90;
const shots = script.shots || [];
if (shots.length > 0) {
  totalFrames = Math.max(...shots.map((s: any) => (s.start || 0) + (s.duration || 90)));
}
if (process.argv[4]) {
  totalFrames = Number(process.argv[4]);
}
console.log(`Auto-detected ${shots.length} shots, ${totalFrames} frames (${(totalFrames / 30).toFixed(1)}s)`);

// Write props for Remotion
const tmpPropsPath = resolve("tmp/script_props.json");
mkdirSync(dirname(tmpPropsPath), { recursive: true });
writeFileSync(tmpPropsPath, JSON.stringify({ script }), "utf-8");

console.log(`Rendering ${script.phase}: ${script.shots?.length || 0} shots, ${totalFrames} frames`);

// Ensure output directory exists
mkdirSync(dirname(resolve(outputPath)), { recursive: true });

// Render with Remotion CLI
const webDir = resolve("web");
const entryPoint = resolve(webDir, "src/remotion/index.ts");
const absOutputPath = resolve(outputPath);

// Use execFileSync with array args to avoid shell escaping issues
const propsJson = readFileSync(tmpPropsPath, "utf-8");
const args = [
  "remotion", "render",
  entryPoint,
  "ScriptDrivenVideo",
  absOutputPath,
  `--props=${propsJson}`,
  "--fps=30",
  "--width=1080",
  "--height=1920",
  `--duration-in-frames=${totalFrames}`,
  "--codec=h264",
];

console.log(`Rendering ${totalFrames} frames...`);

try {
  execFileSync("npx", args, {
    stdio: "inherit",
    cwd: webDir,
    env: { ...process.env },
  });
  console.log(`\n✅ Rendered to ${absOutputPath}`);
} catch (err) {
  console.error("❌ Render failed:", err);
  process.exit(1);
}
