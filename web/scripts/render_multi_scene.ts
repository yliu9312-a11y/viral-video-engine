/**
 * render_multi_scene.ts — 渲染 MultiSceneVideo（场景级分解 → MP4）
 *
 * 用法:
 *   npx tsx scripts/render_multi_scene.ts <decomposition.json> <output.mp4>
 */
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error("用法: npx tsx scripts/render_multi_scene.ts <decomposition.json> <output.mp4>");
    process.exit(1);
  }

  const jsonPath = path.resolve(args[0]);
  const outputPath = path.resolve(args[1]);

  if (!fs.existsSync(jsonPath)) {
    console.error(`JSON 文件不存在: ${jsonPath}`);
    process.exit(1);
  }

  const decomposition = JSON.parse(fs.readFileSync(jsonPath, "utf-8"));

  console.log(`渲染 MultiSceneVideo:`);
  console.log(`  场景数: ${decomposition.scenes?.length || 0}`);
  console.log(`  画布: ${decomposition.canvas_width}x${decomposition.canvas_height} @ ${decomposition.fps}fps`);
  console.log(`  总帧数: ${decomposition.total_frames}`);
  console.log(`  输出: ${outputPath}`);
  console.log(`-------------`);

  const bundled = await bundle({
    entryPoint: path.resolve(__dirname, "../src/remotion/index.ts"),
    webpackOverride: (config) => config,
  });

  const composition = await selectComposition({
    serveUrl: bundled,
    id: "MultiSceneVideo",
    inputProps: { decomposition },
  });

  await renderMedia({
    composition,
    serveUrl: bundled,
    codec: "h264",
    outputLocation: outputPath,
    inputProps: { decomposition },
  });

  const stats = fs.statSync(outputPath);
  console.log(`\n✅ 渲染完成: ${outputPath} (${(stats.size / 1024 / 1024).toFixed(1)} MB)`);
}

main().catch((e) => {
  console.error("渲染失败:", e);
  process.exit(1);
});
