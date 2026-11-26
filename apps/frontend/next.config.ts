import type { NextConfig } from "next"
import { fileURLToPath } from "node:url"

// Server-side only: where the Next.js server forwards /api/v1/* (same origin for the browser,
// required for HttpOnly cookies).
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000"
const PROJECT_ROOT = fileURLToPath(new URL(".", import.meta.url))

const nextConfig: NextConfig = {
  turbopack: { root: PROJECT_ROOT },
  experimental: { proxyTimeout: 120000 },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_INTERNAL_URL}/api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
