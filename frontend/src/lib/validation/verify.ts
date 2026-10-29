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

const BYTES32_HEX = /^0x[0-9a-fA-F]{64}$/;
const LOCAL_DEV_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/**
 * Only https URLs are fetched, plus plain http to a local development host (mirrors the agents'
 * fetcher, plan §16.3 and S-11). caseFileURI and replayReportURI are chosen by whoever posts on
 * chain, so data:, javascript:, ftp: and http to other hosts are refused before any request.
 */
export function isFetchableEvidenceUrl(url: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol === "https:") return true;
  return parsed.protocol === "http:" && LOCAL_DEV_HOSTS.has(parsed.hostname);
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

  if (!BYTES32_HEX.test(expectedHash.trim())) {
    return {
      valid: false,
      computedHash: "",
      expectedHash,
      error: "Expected hash is not a 32-byte hex value",
    };
  }

  const resolved = resolveUri(uri);
  if (!isFetchableEvidenceUrl(resolved)) {
    return {
      valid: false,
      computedHash: "",
      expectedHash,
      error: "Unsupported evidence URI: only https://, ipfs:// and local-development http:// are fetched",
    };
  }

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
