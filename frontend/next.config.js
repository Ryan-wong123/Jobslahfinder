/** @type {import('next').NextConfig} */
const apiRewriteTarget = process.env.NEXT_SERVER_API_BASE_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  devIndicators: false,
  async rewrites() {
    if (process.env.NODE_ENV === "development") {
      return [
        {
          source: "/api/:path*",
          destination: `${apiRewriteTarget}/:path*`
        }
      ];
    }
    return [];
  }
};

module.exports = nextConfig;
