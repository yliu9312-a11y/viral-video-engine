/**
 * Render a ProductPromo composition (landscape 1080x640, 39s).
 *
 * Usage: npx tsx scripts/render_promo.ts <output.mp4>
 */

import { execSync } from "child_process";
import { mkdirSync } from "fs";
import { dirname, resolve } from "path";

const outputPath = process.argv[2] || "output/promo_ai_writing.mp4";

console.log("Rendering ProductPromo: 1080x640, 30fps, 1170 frames (39s)");

mkdirSync(dirname(resolve(outputPath)), { recursive: true });

const webDir = resolve("web");
const entryPoint = resolve(webDir, "src/remotion/index.ts");
const absOutputPath = resolve(outputPath);

const cmd = [
  "npx remotion render",
  entryPoint,
  "ProductPromo",
  absOutputPath,
  "--fps=30",
  "--width=1080",
  "--height=640",
  "--duration-in-frames=1170",
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
