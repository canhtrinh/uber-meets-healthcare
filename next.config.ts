import type { NextConfig } from "next";

const PRIMVOICES_API = "https://api.primvoices.com";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/pv/:path*",
        destination: `${PRIMVOICES_API}/:path*`,
      },
    ];
  },
};

export default nextConfig;
