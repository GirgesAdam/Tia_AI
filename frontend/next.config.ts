import type { NextConfig } from "next";

const allowedDevOrigins = (
  process.env.NEXT_ALLOWED_DEV_ORIGINS || "192.168.1.5"
)
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  allowedDevOrigins,
  experimental: {
    serverActions: { bodySizeLimit: "64mb" },
    proxyClientMaxBodySize: "64mb",
  },
};

export default nextConfig;
