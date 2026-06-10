/**
 * Render a SparkPromo composition (1280x720, 60fps, 31s).
 *
 * Usage: npx tsx scripts/render_spark.ts <output.mp4>
 */

import { execSync } from "child_process";
import { mkdirSync } from "fs";
import { dirname, resolve } from "path";

const outputPath = process.argv[2] || "output/spark_promo.mp4";

console.log("Rendering SparkPromo: 1280x720, 60fps, 1860 frames (31s)");

mkdirSync(dirname(resolve(outputPath)), { recursive: true });

const webDir = resolve("web");
const entryPoint = resolve(webDir, "src/remotion/index.ts");
const absOutputPath = resolve(outputPath);

const cmd = [
  "npx remotion render",
  entryPoint,
  "SparkPromo",
  absOutputPath,
  "--fps=60",
  "--width=1280",
  "--height=720",
  "--duration-in-frames=1860",
  "--codec=h264",
].join(" ");

console.log(`Running: ${cmd}`);

try {
  execSync(cmd, {
    stdio: "inherit",
    cwd: webDir,
    env: { ...process.env },
  });
  console.log(`\n✅ Rendered to ${absOutputPath}`);
} catch (err) {
  console.error("❌ Render failed:", err);
  process.exit(1);
}
