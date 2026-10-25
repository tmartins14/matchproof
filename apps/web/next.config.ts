import type { NextConfig } from "next";

// A production build bakes the API URL into the bundle, so it must be given; only `next dev` may default to localhost.
if (process.env.NODE_ENV === "production" && !process.env.NEXT_PUBLIC_API_URL) {
  throw new Error("NEXT_PUBLIC_API_URL is required for a production build (azd writes it to .env.production.local from API_URL).");
}

const nextConfig: NextConfig = { output: "export" };

export default nextConfig;
