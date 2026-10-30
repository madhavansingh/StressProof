/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // StressProof uses no next/image. Turning the optimizer off removes /_next/image, which has unpatched
  // advisories in Next.js 14.2.x (RCE with crafted AVIF/SVG, DoS, unbounded disk cache). See README,
  // "Supply-chain scan".
  images: { unoptimized: true },
  webpack: (config) => {
    config.externals.push("pino-pretty", "lokijs", "encoding");
    config.resolve.fallback = {
      ...config.resolve.fallback,
      fs: false,
      net: false,
      tls: false,
    };
    config.resolve.alias = {
      ...config.resolve.alias,
      "@react-native-async-storage/async-storage": false,
      "@x402/core/client": false,
      "@x402/evm": false,
      "@x402/evm/exact/client": false,
      "@x402/evm/upto/client": false,
      "@x402/svm/exact/client": false,
    };
    return config;
  },
};

export default nextConfig;
