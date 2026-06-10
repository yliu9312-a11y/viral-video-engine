/**
 * render_multi_scene.ts — 渲染 MultiSceneVideo（场景级分解 → MP4）
 *
 * 用法:
 *   npx tsx scripts/render_multi_scene.ts <decomposition.json> <output.mp4>
 */
import { execFileSync } from "child_process";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { dirname, resolve } from "path";

const args = process.argv.slice(2);
if (args.length < 2) {
  console.error("用法: npx tsx scripts/render_multi_scene.ts <decomposition.json> <output.mp4>");
  process.exit(1);
}

const jsonPath = resolve(args[0]);
const outputPath = resolve(args[1]);

if (!existsSync(jsonPath)) {
  console.error(`JSON 文件不存在: ${jsonPath}`);
  process.exit(1);
}

const decomposition = JSON.parse(readFileSync(jsonPath, "utf-8"));

console.log(`渲染 MultiSceneVideo:`);
console.log(`  场景数: ${decomposition.scenes?.length || 0}`);
console.log(`  画布: ${decomposition.canvas_width}x${decomposition.canvas_height} @ ${decomposition.fps}fps`);
console.log(`  总帧数: ${decomposition.total_frames}`);
console.log(`  输出: ${outputPath}`);
console.log(`-------------`);

// Write props for Remotion CLI
const tmpPropsPath = resolve("tmp/multiscene_props.json");
mkdirSync(dirname(tmpPropsPath), { recursive: true });
writeFileSync(tmpPropsPath, JSON.stringify({ decomposition }), "utf-8");

mkdirSync(dirname(outputPath), { recursive: true });

const webDir = resolve("web");
const entryPoint = resolve(webDir, "src/remotion/index.ts");
const propsJson = readFileSync(tmpPropsPath, "utf-8");
const totalFrames = decomposition.total_frames || 90;
const fps = decomposition.fps || 30;
const width = decomposition.canvas_width || 1280;
const height = decomposition.canvas_height || 720;

const renderArgs = [
  "remotion", "render",
  entryPoint,
  "MultiSceneVideo",
  outputPath,
  `--props=${propsJson}`,
  `--fps=${fps}`,
  `--width=${width}`,
  `--height=${height}`,
  `--duration-in-frames=${totalFrames}`,
  "--codec=h264",
];

console.log(`渲染 ${totalFrames} 帧...`);

try {
  execFileSync("npx", renderArgs, {
    stdio: "inherit",
    cwd: webDir,
    env: { ...process.env },
  });
  console.log(`\n✅ 渲染完成: ${outputPath}`);
} catch (err) {
  console.error("渲染失败:", err);
  process.exit(1);
}
