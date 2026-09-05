import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["@copilotkit/runtime"],
  turbopack: {
    // Keep Turbopack inside this app; parent lockfiles can otherwise change
    // Next's inferred workspace root and make the production build unreadable.
    root: path.resolve(__dirname),
  },
  env: {
    // NEXT_PUBLIC_* resolves at build time while the Runtime reads the project key
    // per request. Provide CPK_INTELLIGENCE_API_KEY during the host build so the
    // browser gate matches the managed Runtime configuration.
    NEXT_PUBLIC_COPILOTKIT_THREADS_ENABLED: process.env.CPK_INTELLIGENCE_API_KEY
      ? "true"
      : "false",
  },
};

export default nextConfig;
