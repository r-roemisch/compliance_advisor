import type { NextConfig } from "next";

// Where the FastAPI backend runs. Rewrites are fixed at build time, so the Docker build
// passes BACKEND_URL=http://backend:8010 as a build argument.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8010";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Self-contained server for the Docker image.
  output: "standalone",
  // Forward /api/* to the backend, so the browser talks to one address only.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
  experimental: {
    // Answers take up to about 30 seconds; the default proxy timeout is 30 seconds.
    proxyTimeout: 120_000,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
