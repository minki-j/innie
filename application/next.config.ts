import type { NextConfig } from "next";
import * as dotenv from "dotenv";
import * as path from "path";

// Load shared root .env so vars like PREFECT_API_KEY are available to all sub-projects
dotenv.config({ path: path.resolve(__dirname, "../.env"), override: false });

const nextConfig: NextConfig = {
  devIndicators: false,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'i.ytimg.com',
      },
      {
        protocol: 'https',
        hostname: 'yt3.ggpht.com',
      },
      {
        protocol: 'https',
        hostname: 'lh3.googleusercontent.com',
      },
    ],
  },
};

export default nextConfig;
