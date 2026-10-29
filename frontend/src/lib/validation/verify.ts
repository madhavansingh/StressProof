import { keccak256 } from "viem";

export const DEFAULT_IPFS_GATEWAY =
  process.env.NEXT_PUBLIC_IPFS_GATEWAY || "https://ipfs.io";

/**
 * Rewrites ipfs:// URIs to an HTTP gateway per implementationplan §19.3.
 */
export function resolveUri(uri: string, gateway: string = DEFAULT_IPFS_GATEWAY): string {
  if (!uri) return "";
  if (uri.startsWith("ipfs://")) {
    const cleanGateway = gateway.replace(/\/+$/, "");
    const cid = uri.slice(7);
    return `${cleanGateway}/ipfs/${cid}`;
  }
  return uri;
}

export interface VerificationResult {
  valid: boolean;
  computedHash: string;
  expectedHash: string;
  error?: string;
  rawJson?: any;
  bytesLength?: number;
}

/**
 * Directly hashes raw Uint8Array bytes using Keccak-256 without re-serialization.
 */
export function verifyBytes(
  bytes: Uint8Array,
  expectedHash: string
): VerificationResult {
  try {
    const computedHash = keccak256(bytes);
    const valid = computedHash.toLowerCase() === expectedHash.trim().toLowerCase();

    let rawJson: any = null;
    try {
      const decoder = new TextDecoder();
      rawJson = JSON.parse(decoder.decode(bytes));
    } catch {
      // not JSON or malformed JSON
    }

    return {
      valid,
      computedHash,
      expectedHash,
      bytesLength: bytes.length,
      rawJson,
    };
  } catch (err: any) {
    return {
      valid: false,
      computedHash: "",
      expectedHash,
      error: err.message || "Failed to hash bytes",
    };
  }
}

/**
 * Fetches raw bytes from URI with cache: 'no-store' and computes Keccak-256.
 * Matches implementationplan.md §7.3 and §19.3.
 */
export async function verifyEvidenceUri(
  uri: string,
  expectedHash: string
): Promise<VerificationResult> {
  if (!uri || !expectedHash) {
    return {
      valid: false,
      computedHash: "",
      expectedHash: expectedHash || "",
      error: "Missing URI or expected hash",
    };
  }

  const resolved = resolveUri(uri);

  try {
    const res = await fetch(resolved, {
      cache: "no-store",
    });

    if (!res.ok) {
      return {
        valid: false,
        computedHash: "",
        expectedHash,
        error: `HTTP ${res.status}: ${res.statusText || "Fetch failed"}`,
      };
    }

    const buffer = await res.arrayBuffer();
    const rawBytes = new Uint8Array(buffer);
    return verifyBytes(rawBytes, expectedHash);
  } catch (err: any) {
    return {
      valid: false,
      computedHash: "",
      expectedHash,
      error: err.message || "Failed to fetch evidence from URI",
    };
  }
}
