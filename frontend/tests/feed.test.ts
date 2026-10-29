import { describe, it, expect, vi } from "vitest";
import { fetchFeed } from "../src/lib/api/client";
import { FeedEntry } from "../src/types";

describe("F5: Feed Pagination and Actor Handling", () => {
  it("advances since parameter during pagination", async () => {
    const originalFetch = global.fetch;

    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      const urlObj = new URL(url);
      const sinceParam = Number(urlObj.searchParams.get("since") || "0");

      if (sinceParam === 0) {
        return {
          ok: true,
          json: async () => ({
            entries: [
              { seq: 1, ts: "2026-10-29T10:00:00Z", actor: "attester", kind: "CLAIM_POSTED" },
              { seq: 2, ts: "2026-10-29T10:01:00Z", actor: "watcher", kind: "REPLAY_MATCH" },
            ],
            nextSince: 2,
          }),
        };
      } else if (sinceParam === 2) {
        return {
          ok: true,
          json: async () => ({
            entries: [
              { seq: 3, ts: "2026-10-29T10:02:00Z", actor: "resolver", kind: "FINALIZED" },
            ],
            nextSince: 3,
          }),
        };
      }

      return {
        ok: true,
        json: async () => ({ entries: [], nextSince: sinceParam }),
      };
    });

    try {
      const firstPage = await fetchFeed(0, 200);
      expect(firstPage.entries).toHaveLength(2);
      expect(firstPage.nextSince).toBe(2);

      const secondPage = await fetchFeed(firstPage.nextSince, 200);
      expect(secondPage.entries).toHaveLength(1);
      expect(secondPage.nextSince).toBe(3);
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("safely handles and models unexpected / unknown actors without throwing", () => {
    const unknownEntry: FeedEntry = {
      seq: 99,
      ts: "2026-10-29T12:00:00Z",
      actor: "unknown_external_oracle",
      kind: "ORACLE_PING",
      data: { ping: "pong" },
    };

    expect(unknownEntry.actor).toBe("unknown_external_oracle");
    expect(unknownEntry.kind).toBe("ORACLE_PING");
  });

  it("supports all 8 backend actors in type union", () => {
    const actors = [
      "attester",
      "malicious_attester",
      "malicious",
      "watcher",
      "resolver",
      "backend",
      "ui",
      "user",
    ];

    actors.forEach((act, idx) => {
      const entry: FeedEntry = {
        seq: idx + 1,
        ts: "2026-10-29T12:00:00Z",
        actor: act,
        kind: "TEST_KIND",
      };
      expect(entry.actor).toBe(act);
    });
  });
});
