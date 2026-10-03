import { build } from "esbuild";
import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(root, "dist");
const apiBaseUrl = process.env.VITE_API_BASE_URL || "http://localhost:8000";

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

const common = {
  bundle: true,
  sourcemap: true,
  target: "es2022",
  platform: "browser",
  define: { API_BASE_URL: JSON.stringify(apiBaseUrl) },
};

await Promise.all([
  build({ ...common, entryPoints: [resolve(root, "src/background/serviceWorker.ts")], outfile: resolve(outDir, "background.js") }),
  build({ ...common, format: "iife", entryPoints: [resolve(root, "src/content/main.ts")], outfile: resolve(outDir, "content.js") }),
  build({ ...common, entryPoints: [resolve(root, "src/sidepanel/main.ts")], outfile: resolve(outDir, "sidepanel.js") }),
]);

await cp(resolve(root, "src/sidepanel/index.html"), resolve(outDir, "sidepanel.html"));
await cp(resolve(root, "src/sidepanel/styles.css"), resolve(outDir, "styles.css"));
await cp(resolve(root, "public/manifest.json"), resolve(outDir, "manifest.json"));
await writeFile(resolve(outDir, "api-base-url.txt"), apiBaseUrl, "utf8");
