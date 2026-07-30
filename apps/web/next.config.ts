import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const API_ORIGIN = process.env.JAMASP_API_ORIGIN ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  async rewrites() {
    // Same-origin by design: the session cookie is httpOnly and SameSite=Lax, so a
    // cross-site request would silently drop it. Proxying also removes CORS from
    // the picture entirely.
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default withNextIntl(nextConfig);
