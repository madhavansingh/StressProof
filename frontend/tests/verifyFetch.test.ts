import { afterEach, describe, expect, it, vi } from "vitest";
import { keccak256, toBytes } from "viem";
import { isFetchableEvidenceUrl, verifyEvidenceUri } from "../src/lib/validation/verify";

const BODY = toBytes('{"schemaVersion":1}');
const HASH = keccak256(BODY);

function mockFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("verifyEvidenceUri through the fetch path", () => {
  it("is valid when the fetched raw bytes hash to the expected value, fetched with no-store", async () => {
    const fetchMock = mockFetch(async () => new Response(new Uint8Array(BODY), { status: 200 }));
    const result = await verifyEvidenceUri("https://backend.example/case-files/x", HASH);
    expect(result.valid).toBe(true);
    expect(result.computedHash).toBe(HASH);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
  });

  it("is invalid after a one-byte change in the served bytes", async () => {
    const mutated = new Uint8Array(BODY);
    mutated[mutated.length - 2] ^= 0x01;
    mockFetch(async () => new Response(mutated, { status: 200 }));
    const result = await verifyEvidenceUri("https://backend.example/case-files/x", HASH);
    expect(result.valid).toBe(false);
    expect(result.computedHash).not.toBe(HASH);
  });

  it("judges integrity only: bytes that are not JSON still verify when the hash matches", async () => {
    const garbage = toBytes("not json at all");
    mockFetch(async () => new Response(new Uint8Array(garbage), { status: 200 }));
    const result = await verifyEvidenceUri("https://backend.example/case-files/x", keccak256(garbage));
    expect(result.valid).toBe(true);
    expect(result.rawJson).toBeNull();
  });

  it("reports a backend HTTP error without a hash", async () => {
    mockFetch(async () => new Response("gone", { status: 404, statusText: "Not Found" }));
    const result = await verifyEvidenceUri("https://backend.example/case-files/x", HASH);
    expect(result.valid).toBe(false);
    expect(result.computedHash).toBe("");
    expect(result.error).toContain("HTTP 404");
  });

  it("reports a network failure (backend down)", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    const result = await verifyEvidenceUri("https://backend.example/case-files/x", HASH);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("Failed to fetch");
  });

  it.each([
    "data:application/json,%7B%7D",
    "javascript:alert(1)",
    "ftp://host/file",
    "http://evil.example/case-files/x",
    "not a url",
  ])("refuses to fetch %s", async (uri) => {
    const fetchMock = mockFetch(async () => new Response(new Uint8Array(BODY), { status: 200 }));
    const result = await verifyEvidenceUri(uri, HASH);
    expect(result.valid).toBe(false);
    expect(result.error).toMatch(/unsupported evidence uri/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses a malformed expected hash without fetching", async () => {
    const fetchMock = mockFetch(async () => new Response(new Uint8Array(BODY), { status: 200 }));
    const result = await verifyEvidenceUri("https://backend.example/case-files/x", "0x1234");
    expect(result.valid).toBe(false);
    expect(result.error).toMatch(/expected hash/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rewrites ipfs:// to the https gateway before fetching", async () => {
    const fetchMock = mockFetch(async () => new Response(new Uint8Array(BODY), { status: 200 }));
    const result = await verifyEvidenceUri("ipfs://bafyexample", HASH);
    expect(result.valid).toBe(true);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/^https:\/\/.+\/ipfs\/bafyexample$/);
  });
});

describe("isFetchableEvidenceUrl", () => {
  it("allows https anywhere and http only for local development hosts", () => {
    expect(isFetchableEvidenceUrl("https://stressproof.example/case-files/x")).toBe(true);
    expect(isFetchableEvidenceUrl("http://127.0.0.1:8000/case-files/x")).toBe(true);
    expect(isFetchableEvidenceUrl("http://localhost:8000/case-files/x")).toBe(true);
    expect(isFetchableEvidenceUrl("http://10.0.0.1/case-files/x")).toBe(false);
    expect(isFetchableEvidenceUrl("data:text/plain,hi")).toBe(false);
  });
});
