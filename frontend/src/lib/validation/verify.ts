import { keccak256 } from "viem";

export interface VerificationResult {
  valid: boolean;
  computedHash: string;
  expectedHash: string;
  error?: string;
  rawJson?: any;
}

/**
 * Fetches raw bytes from URI and computes Keccak-256 without re-serialization.
 * Matches implementationplan.md §7.3 and §19.
 */
export async function verifyEvidenceUri(
  uri: string,
  expectedHash: string
): Promise<VerificationResult> {
  try {
    const res = await fetch(uri);
    if (!res.ok) {
      return {
        valid: false,
        computedHash: "",
        expectedHash,
        error: `HTTP ${res.status}: ${res.statusText}`,
      };
    }

    const buffer = await res.arrayBuffer();
    const rawBytes = new Uint8Array(buffer);
    const computedHash = keccak256(rawBytes);

    const valid = computedHash.toLowerCase() === expectedHash.toLowerCase();

    let rawJson: any = null;
    try {
      const decoder = new TextDecoder();
      rawJson = JSON.parse(decoder.decode(rawBytes));
    } catch {
      // Keep null if not JSON
    }

    return {
      valid,
      computedHash,
      expectedHash,
      rawJson,
    };
  } catch (err: any) {
    return {
      valid: false,
      computedHash: "",
      expectedHash,
      error: err.message || "Failed to fetch evidence",
    };
  }
}
