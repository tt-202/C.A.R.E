import type { CapacitorConfig } from "@capacitor/cli";
import { loadEnvConfig } from "@next/env";

const projectDir = process.cwd();
loadEnvConfig(projectDir);

/**
 * URL the native shell loads in the WebView (your Vercel deployment).
 * Set CAPACITOR_SERVER_URL in .env (see .env.example). No trailing slash.
 */
const rawUrl =
  process.env.CAPACITOR_SERVER_URL ?? process.env.NEXT_PUBLIC_APP_URL;
const serverUrl = rawUrl?.replace(/\/$/, "");

const config: CapacitorConfig = {
  /** Must be unique in Apple’s system — use your own reverse-DNS id (e.g. com.yourname.care). */
  appId: "com.tuyentran.care",
  appName: "C.A.R.E",
  webDir: "www",
  server: serverUrl
    ? {
        url: serverUrl,
        cleartext: false,
      }
    : undefined,
};

export default config;
