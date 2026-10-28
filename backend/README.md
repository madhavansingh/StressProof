# stressproof-backend

FastAPI service for StressProof: content-addressed evidence storage, `/stress/run` replay execution,
and the agent activity feed. It never touches the chain.

## Endpoints
| Method and path | Auth | Notes |
|---|---|---|
| `GET /health` | — | `{ok, service, version, gitCommit, datasets, storage}` |
| `GET /datasets` | — | `[{datasetId, dataClass, forkBlock, counts, snapshotHash}]` |
| `GET /datasets/{id}/manifest` | — | Raw manifest bytes. 400 malformed id, 404 unknown |
| `POST /stress/run` | Bearer | Builds, validates and stores a case file. 404 unknown dataset, 422 bad scenario |
| `GET /case-files/{hash}` | — | Exact stored bytes, `X-Content-Keccak256`, immutable cache. 400 / 404 |
| `POST /case-files` | Bearer | Raw canonical bytes, must pass `validate()`. 201 new, 200 existing, 413, 422 |
| `GET /replay-reports/{hash}` | — | Exact stored bytes. 400 / 404 |
| `POST /replay-reports` | Bearer | Canonical replay report. 201 / 200 / 413 / 422 |
| `POST /feed` | Bearer | `{actor, kind, claimId?, txHash?, data?}` → `{seq}` |
| `GET /feed?since=&limit=` | — | `{entries, nextSince}` |
| `GET /graph/exposure` | — | Phase 2: 503 until the graph exists |

Writes need `Authorization: Bearer $API_WRITE_TOKEN` (401 missing, 403 wrong).

## Storage
| `DATABASE_URL` | Backend | Use |
|---|---|---|
| unset | Filesystem under `DATA_DIR` (`case-files/`, `replay-reports/`, `replay_outputs/`, `feed.jsonl`) | Local development, tests, hosts with a persistent disk |
| set | PostgreSQL (tables `blobs`, `feed`, created automatically) | Free hosting tiers, whose disk is wiped on restart or redeploy |

Both backends have the same HTTP behaviour. Blobs are keyed by keccak256 of their exact bytes and
never modified; the feed `seq` is unique and survives restarts. Datasets are read-only files loaded
from `DATASETS_DIR` (default `DATA_DIR/datasets`, then `data/fixtures/datasets`, which is committed).

## Configuration
| Variable | Default | Notes |
|---|---|---|
| `API_WRITE_TOKEN` | dev default | **Set a secret for any deployment.** Startup is refused if it is empty, or if it is the dev default while `DATABASE_URL` is set; file mode only warns |
| `BACKEND_PUBLIC_URL` | `http://127.0.0.1:8000` | Base of the `caseFileURI` / `reportURI` values it returns |
| `DATABASE_URL` | empty | e.g. `postgresql://user:pass@host/db?sslmode=require` (Neon, Supabase) |
| `DATABASE_SCHEMA` | `public` | |
| `DATA_DIR` | `./data` | Relative paths resolve against the repo root |
| `DATASETS_DIR` | see above | Comma-separated roots; the first root wins on duplicate ids |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated; never a wildcard |
| `MARKET_ID_STRING` | `aave-v3-eth-weth-stable` | |
| `GIT_COMMIT` | `git rev-parse HEAD` | Recorded as `model.replayerCommit`; set it where `.git` is absent |
| `MAX_BODY_BYTES` | 25 MB | |

## Run
```bash
make backend                      # development, filesystem storage, auto-reload
uv run uvicorn stressproof_backend.main:app --host 0.0.0.0 --port $PORT --workers 1   # deployment
```

## Deploying on a free tier (e.g. Render + Neon)
1. Create a free Postgres database (Neon or Supabase) and copy its connection string.
2. Set `DATABASE_URL`, a random `API_WRITE_TOKEN`, `BACKEND_PUBLIC_URL` (the service's public URL),
   `CORS_ORIGINS` (the frontend URL) and `GIT_COMMIT` (if the build has no `.git`).
3. Start command: the deployment `uvicorn` line above. `GET /health` must report `"storage":"postgres"`.
4. Give agents and the frontend the same `API_WRITE_TOKEN` and the backend URL.

## Tests
```bash
uv run pytest backend/tests -q                                         # filesystem backend
TEST_DATABASE_URL=postgresql://... uv run pytest backend/tests -q      # also runs every test on Postgres
```
