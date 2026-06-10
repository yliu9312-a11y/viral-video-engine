/**
 * render_style.ts — 渲染 StyleDrivenVideo 合成
 *
 * Usage: npx tsx scripts/render_style.ts <scene.json> <output.mp4>
 */
import { execFileSync } from "child_process";
import { readFileSync } from "fs";
import { resolve } from "path";

const PROJECT_ROOT = resolve(__dirname, "..");

const scenePath = process.argv[2];
const outputPath = process.argv[3] || "output/style_video.mp4";

if (!scenePath) {
  console.error("Usage: npx tsx scripts/render_style.ts <scene.json> <output.mp4>");
  process.exit(1);
}

const scene = JSON.parse(readFileSync(scenePath, "utf-8"));
const fps = scene.fps || 30;
const width = scene.canvas_width || 1080;
const height = scene.canvas_height || 1920;
const durationInFrames = scene.duration || 600;

console.log(`Rendering StyleDrivenVideo: ${width}x${height} @ ${fps}fps, ${durationInFrames} frames`);
console.log(`Scene: ${scenePath}`);
console.log(`Output: ${outputPath}`);

// 生成 props JSON
const propsPath = resolve(PROJECT_ROOT, "data", "output", "style_props.json");
const props = { scene };
require("fs").writeFileSync(propsPath, JSON.stringify(props));

// 调用 npx remotion render
const webDir = resolve(PROJECT_ROOT, "web");
const entryPoint = resolve(webDir, "src/remotion/index.ts");
const absOutputPath = resolve(outputPath);

// 读取 props 文件内容作为命令行参数
const propsJson = readFileSync(propsPath, "utf-8");
const args = [
  "remotion", "render",
  entryPoint,
  "StyleDrivenVideo",
  absOutputPath,
  `--props=${propsJson}`,
  `--fps=${fps}`,
  `--width=${width}`,
  `--height=${height}`,
  `--duration-in-frames=${durationInFrames}`,
  "--codec=h264",
];

try {
  execFileSync("npx", args, {
    cwd: webDir,
    stdio: "inherit",
    timeout: 300_000,
  });
  console.log(`\n✅ Rendered to ${outputPath}`);
} catch (err: any) {
  console.error(`\n❌ Render failed: ${err.message}`);
  process.exit(1);
}
