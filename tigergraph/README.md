# TigerGraph integration (WP-2 to WP-5)

The graph holds one deterministic replay per case file: accounts, assets, market, dataset, case file, and the
per-account replay outcomes. It answers **estimated exposure** questions. It is **never** part of a claim
verdict: verdicts come only from deterministic replay.

| File | What it is |
|---|---|
| `schema.gsql` | Vertex and edge types (`SP_` prefix) and graph `StressProof` (plan §17.1, C-05 composite ids) |
| `queries/sp_exposure.gsql` | Read-only exposure query for one case file: outcome totals plus top accounts by residual bad debt |
| `data/*.csv` | Rows generated from the golden **SYNTHETIC** fixture `data/fixtures/casefile_v1.json` by `cli export` |
| `backend/src/stressproof_backend/tigergraph/` | REST client, row builder, loader and reconciler, exposure service, CLI |

## Status (2026-10-30, frozen for submission)

- Schema: **created** in TigerGraph Savanna by the project owner (5 vertex types, 6 edge types).
- CSV data loading: **pending**. The graph holds no StressProof data yet.
- The app shows **TIGERGRAPH UNAVAILABLE** and uses the local SYNTHETIC replay graph. No TigerGraph result is
  displayed or claimed.
- To finish later: set the `TG_*` values in `.env`, then run `load`, `reconcile`, `install` and `query` below.
  Loading uses the REST++ API, not manual uploads.

## Connection check (read-only)

```bash
uv run python -m stressproof_backend.tigergraph.cli check
```

Also available from the running backend as `GET /graph/tigergraph/health`.

- **Auth:** the database secret is sent as `Authorization: GSQL-Secret <secret>`. If that is refused, a REST++
  token is minted from the same secret.
- **What it does:** it reads the graph schema only, and reports the vertex and edge types plus whether all 5
  expected vertex types and 6 expected edge types exist.
- **Host:** `TG_HOST` must be the exact workspace endpoint from Savanna (workspace > Connect > Connect from
  API), as an https origin with no path. A hostname that does not resolve is reported as a DNS error.

## Data (SYNTHETIC)

Generated from the case file and `stressproof_core.replay`; nothing is inferred. Every vertex carries
`data_class = SYNTHETIC`.

| Type | Rows | Source |
|---|---|---|
| `SP_Dataset` | 1 | case file `dataset` |
| `SP_Market` | 1 | `marketId` |
| `SP_Asset` | 2 | WETH collateral parameters; one aggregate stablecoin-debt vertex (per-token split not recorded) |
| `SP_Account` | 6 | `snapshot.accounts` (`collateral_usd8` = unshocked value) |
| `SP_CaseFile` | 1 | evidence hash and committed `results` |
| `SP_INCLUDED_IN`, `SP_COLLATERAL_IN`, `SP_BORROWS` | 6 each | account positions |
| `SP_LISTS` | 2 | market → assets |
| `SP_REPLAYS` | 1 | case file → market |
| `SP_OUTCOME` | 6 | `replay()` per-account outcomes |

That is 11 vertices and 27 edges in total. Expected totals: 4 liquidatable accounts; residual bad debt
200000000001; liquidation volume 3174300000001; debt at risk 3374300000002 (USD, 8 decimals). There are no claim
vertices, because the golden fixture has no on-chain claim.

## Setup (needs your Savanna workspace)

1. In TigerGraph Savanna, create or start a workspace. TigerGraph 4.x, any size; the free tier is enough.
2. In the workspace, create a **database user** that can create a global schema and install queries (setup
   only). Then create a **secret** for REST++ tokens; it is shown once. Read-only use needs only the secret.
3. Put the values in the repository `.env`. It is git-ignored; never use `NEXT_PUBLIC_` names for these:
   ```
   TG_HOST=https://<workspace-id>.i.tgcloud.io
   TG_GRAPH=StressProof
   TG_USERNAME=<database user>
   TG_PASSWORD=<password>
   TG_SECRET=<secret>
   ```
4. Run, from the repository root:
   ```bash
   uv run python -m stressproof_backend.tigergraph.cli check
   uv run python -m stressproof_backend.tigergraph.cli schema
   uv run python -m stressproof_backend.tigergraph.cli install
   uv run python -m stressproof_backend.tigergraph.cli load
   uv run python -m stressproof_backend.tigergraph.cli reconcile
   uv run python -m stressproof_backend.tigergraph.cli query
   ```
   - `load` is idempotent: upserts by primary id.
   - `reconcile` exits 1 on any count, total or label difference.
   - Load another case file with `--case-file data/case-files/<hash>.json`.
5. Restart the backend. `GET /graph/exposure?evidenceHash=<hash>` then serves the live query, and `/graph`
   shows **REAL TIGERGRAPH RESULTS** (plus **SYNTHETIC FIXTURE DATA** for the fixture).

If the GSQL REST route is refused on your workspace, paste `schema.gsql` and then `queries/sp_exposure.gsql`
into the workspace's GSQL editor instead. Then run `load`, `reconcile` and `query`, which use only REST++.

## API behaviour

| Case | `GET /graph/exposure` |
|---|---|
| TigerGraph answers and the case file is loaded | 200, `source: "tigergraph"`, totals, top accounts, reconciliation against the stored case file |
| Case file not in the graph | 404 `notLoaded` |
| `TG_HOST` unset, bad credentials, workspace paused, network error | 503 `unavailable`, with a reason and no data |
| Malformed `evidenceHash`, or `top` outside 1–50 | 400 / 422 |

The backend never returns local or mock data as a TigerGraph result. Secrets stay in the backend process.
