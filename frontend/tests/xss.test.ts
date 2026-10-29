import { describe, it, expect } from "vitest";
import { isValidExternalLink, escapeHtml } from "../src/lib/validation/security";

describe("T-F-05: XSS and URI Scheme Security", () => {
  it("escapes a rationale containing <script> so it renders strictly as text", () => {
    const maliciousRationale = 'Malicious agent test <script>alert("pwned")</script> rationale';
    const escaped = escapeHtml(maliciousRationale);

    expect(escaped).not.toContain("<script>");
    expect(escaped).toContain("&lt;script&gt;");
    expect(escaped).toContain("&lt;/script&gt;");
  });

  it("permits only https: or ipfs: links", () => {
    // Allowed safe links
    expect(isValidExternalLink("https://ipfs.io/ipfs/bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi")).toBe(true);
    expect(isValidExternalLink("https://aave.com")).toBe(true);
    expect(isValidExternalLink("ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi")).toBe(true);

    // Disallowed unsafe or malformed links
    expect(isValidExternalLink("javascript:alert(1)")).toBe(false);
    expect(isValidExternalLink("javascript:void(0)")).toBe(false);
    expect(isValidExternalLink("data:text/html,<script>alert(1)</script>")).toBe(false);
    expect(isValidExternalLink("file:///etc/passwd")).toBe(false);
    expect(isValidExternalLink("ftp://malicious.host")).toBe(false);
    expect(isValidExternalLink("not-a-valid-url")).toBe(false);
  });
});
