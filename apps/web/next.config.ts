import type { NextConfig } from "next";

/**
 * Same-origin deployment: the browser only ever talks to this origin. Next proxies the
 * API and its health probes to the API service, so the httpOnly session cookie stays
 * first-party and no CORS is needed. In production a load balancer may route these paths
 * straight to the API before they reach Next.
 *
 * Live updates are WebSockets under /ws, proxied the same way: the Next server upgrades
 * the connection to the API, so the agent's session cookie stays first-party there too.
 * The API pings every 25 seconds; the proxy timeout is well above that.
 *
 * API_URL is the API's address as this server reaches it (API_INTERNAL_URL is accepted
 * for older env files).
 */
const apiInternal = (process.env.API_URL || process.env.API_INTERNAL_URL || "http://localhost:4830").replace(/\/+$/, "");

const prod = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  // One self-contained server bundle (`node server.js`), the unit a container image ships.
  output: "standalone",
  outputFileTracingRoot: __dirname,
  poweredByHeader: false,
  devIndicators: false,
  reactStrictMode: true,
  experimental: { proxyTimeout: 120_000 },
  async rewrites() {
    // afterFiles rewrites: the app's own route handlers (/api/healthz) win over the proxy.
    return [
      { source: "/api/:path*", destination: `${apiInternal}/api/:path*` },
      { source: "/ws/:path*", destination: `${apiInternal}/ws/:path*` },
      { source: "/healthz", destination: `${apiInternal}/healthz` },
      { source: "/readyz", destination: `${apiInternal}/readyz` },
      { source: "/docs", destination: `${apiInternal}/docs` },
      { source: "/openapi.json", destination: `${apiInternal}/openapi.json` },
    ];
  },
  async headers() {
    const common = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
      // Browsers honour HSTS only over HTTPS, so this is inert on http://localhost.
      ...(prod ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }] : []),
    ];
    // The Content-Security-Policy (with frame-ancestors) is set per request in middleware.ts:
    // only the widget frame may be embedded, and only by the inbox's allowed sites.
    return [
      { source: "/:path*", headers: common },
      // The loader is embedded on customer sites: let any origin fetch it, cache briefly.
      { source: "/widget.js", headers: [{ key: "Cache-Control", value: "public, max-age=300" }, { key: "Access-Control-Allow-Origin", value: "*" }] },
    ];
  },
};

export default nextConfig;
