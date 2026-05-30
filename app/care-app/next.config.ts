import { createRequire } from "module";
import path from "path";
import type { NextConfig } from "next";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  /** Avoid picking a parent folder lockfile as the tracing root on some machines. */
  outputFileTracingRoot: path.join(__dirname),
  /**
   * `shadcn` only exposes `./tailwind.css` under the package `"style"` export condition.
   * Webpack's CSS pipeline often does not use that condition, so Vercel/Linux builds fail.
   * Alias to the real file so `@import "shadcn/tailwind.css"` always resolves.
   */
  webpack: (config) => {
    try {
      const shadcnPkg = require.resolve("shadcn/package.json");
      const shadcnTailwind = path.join(path.dirname(shadcnPkg), "dist", "tailwind.css");
      config.resolve = config.resolve ?? {};
      config.resolve.alias = {
        ...(config.resolve.alias as Record<string, string | false | string[]>),
        "shadcn/tailwind.css": shadcnTailwind,
      };
    } catch {
      /* optional */
    }
    return config;
  },
};

export default nextConfig;
