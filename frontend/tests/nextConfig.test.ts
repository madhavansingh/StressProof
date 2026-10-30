import { describe, it, expect } from "vitest";
import nextConfig from "../next.config.mjs";

describe("next.config hardening (WP-1 dependency audit)", () => {
  it("disables the Image Optimization API, which StressProof never uses", () => {
    // Next.js 14.2.x has unpatched advisories in /_next/image, including unauthenticated RCE with crafted
    // AVIF/SVG files (GHSA-2xp9-vwfh-vxw4, GHSA-2464-fhr4-w9xw) and DoS/disk-growth issues. The app imports
    // no next/image and serves no public images, so turning the optimizer off removes the endpoint's attack
    // surface without a version change.
    expect(nextConfig.images?.unoptimized).toBe(true);
  });

  it("keeps the existing build settings", () => {
    expect(nextConfig.reactStrictMode).toBe(true);
    expect(typeof nextConfig.webpack).toBe("function");
  });
});
