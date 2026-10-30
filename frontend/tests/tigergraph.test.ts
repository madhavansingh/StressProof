import { describe, it, expect } from "vitest";
import { fetchTigerGraphExposure, parseExposure, tigerGraphLabels } from "@/lib/graph/tigergraph";

const HASH = "0x7f427d2c66ff24dd70014a717706d17a25d0070d67c16f69cd1ae9f3777a25f0";
const LIVE = {
  status: "ok", source: "tigergraph", host: "ws.i.tgcloud.io", graph: "StressProof", query: "sp_exposure", dataClass: "SYNTHETIC",
  totals: { accounts: "6", liquidatable_accounts: "4", residual_bad_debt_usd8: "200000000001", liquidation_volume_usd8: "3174300000001", debt_at_risk_usd8: "3374300000002" },
  topExposures: [{ account_id: "synth-0002", origin: "synthetic", data_class: "SYNTHETIC", liquidatable: true, debt_usd8: "1200000000000",
    collateral_usd8: "1500000000000", collateral_value_usd8: "1050000000000", repaid_usd8: "1000000000000", residual_usd8: "200000000000" }],
  reconciliation: { status: "matched", checks: [{ name: "residual_bad_debt_usd8", tigergraph: "200000000001", caseFile: "200000000001", matches: true }] },
};

const reply = (status: number, body: unknown) => async () => new Response(JSON.stringify(body), { status });

describe("TigerGraph exposure client", () => {
  it("accepts a live TigerGraph reply and labels synthetic data", async () => {
    const r = await fetchTigerGraphExposure(HASH, "http://b.test", reply(200, LIVE));
    expect(r.status).toBe("live");
    expect(tigerGraphLabels(r)).toEqual({ source: "REAL TIGERGRAPH RESULTS", dataClass: "SYNTHETIC FIXTURE DATA" });
    if (r.status === "live") expect(r.data.rows[0].accountId).toBe("synth-0002");
  });

  it("never treats a reply without source=tigergraph as live", async () => {
    const r = await fetchTigerGraphExposure(HASH, "http://b.test", reply(200, { ...LIVE, source: "replay_outputs" }));
    expect(r.status).toBe("unavailable");
    expect(tigerGraphLabels(r).source).toBe("TIGERGRAPH UNAVAILABLE");
  });

  it.each([
    ["a non-integer total", { ...LIVE, totals: { ...LIVE.totals, accounts: "6.5" } }],
    ["markup in a row", { ...LIVE, topExposures: [{ ...LIVE.topExposures[0], account_id: "<img src=x>\u0000" }] }],
    ["a bad reconciliation status", { ...LIVE, reconciliation: { status: "ok", checks: [] } }],
  ])("rejects %s", (_n, body) => {
    expect(parseExposure(body)).toBeNull();
  });

  it("reports 503 and network failures as unavailable", async () => {
    const down = await fetchTigerGraphExposure(HASH, "http://b.test", reply(503, { status: "unavailable", detail: "TigerGraph is not configured on this backend (TG_HOST unset)" }));
    expect(down).toEqual({ status: "unavailable", detail: "TigerGraph is not configured on this backend (TG_HOST unset)" });
    const net = await fetchTigerGraphExposure(HASH, "http://b.test", async () => { throw new TypeError("Failed to fetch"); });
    expect(net).toEqual({ status: "unavailable", detail: "Backend unreachable: Failed to fetch" });
  });

  it("distinguishes a case file that is not loaded", async () => {
    const r = await fetchTigerGraphExposure(HASH, "http://b.test", reply(404, { status: "notLoaded" }));
    expect(r).toEqual({ status: "notLoaded" });
    expect(tigerGraphLabels(r).source).toBe("TIGERGRAPH CONNECTED: CASE FILE NOT LOADED");
  });

  it("does not call the backend for a malformed hash", async () => {
    let called = false;
    const r = await fetchTigerGraphExposure("0x123", "http://b.test", async () => { called = true; return new Response("{}"); });
    expect(r.status).toBe("unavailable");
    expect(called).toBe(false);
  });
});
