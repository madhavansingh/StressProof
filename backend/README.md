# stressproof-backend

FastAPI service for StressProof managing content-addressed evidence storage, replay execution, and the agent activity feed.

## Endpoints
* `GET /health`: Health check and loaded datasets.
* `GET /datasets`: List registered dataset manifests.
* `POST /stress/run`: Executes a stress scenario on a snapshot, builds and stores the case file, and returns `evidenceHash` and `caseFileURI`.
* `GET /case-files/{evidenceHash}`: Serves exact raw stored bytes of a case file.
* `POST /case-files`: Ingests a raw canonical case file.
* `GET /replay-reports/{hash}`: Serves exact raw bytes of a watcher replay report.
* `POST /replay-reports`: Ingests a watcher replay report.
* `GET /feed`: Returns append-only agent feed entries.
* `POST /feed`: Appends an agent activity log entry.
