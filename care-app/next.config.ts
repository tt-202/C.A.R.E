import path from "path";
import type { NextConfig } from "next";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  /** Avoid picking a parent folder lockfile as the tracing root on some machines. */
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
