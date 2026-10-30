# StressProof — Repository Structure

This monorepo is structured for strict separation of concerns, rapid local developer feedback, and isolated dependency management.

---

## Directory Hierarchy

```text
StressProof/
├── README.md                      # Project introduction, developer quickstart, disclosure
├── CONTRIBUTING.md                # Development workflow, PR guidelines, code standards
├── Makefile                       # Top-level orchestration commands
├── .gitignore                     # Repository-wide ignore patterns
├── .editorconfig                  # Formatting and indentation rules
├── .env.example                   # Environment configuration template
├── pyproject.toml                 # Root Python workspace configuration (uv)
├── pnpm-workspace.yaml            # Root Node/pnpm workspace configuration
│
├── docs/                          # Comprehensive technical documentation & specifications
│   ├── implementationplan.md      # Ground truth implementation roadmap & corrections
│   ├── StressProof_Final.md       # Original specification (v2)
│   ├── architecture.md            # System architecture and trust boundaries
│   ├── repository-structure.md    # This file
│   ├── developer-setup.md         # Environment setup per developer role
│   ├── team-ownership.md          # Ownership, handoff points, and review matrix
│   ├── integration-contracts.md   # ABIs, REST APIs, and event definitions
│   ├── security.md                # Threat model and security mitigations
│   └── schemas/                   # Normative JSON data schemas
│       ├── README.md              # Schema catalog and serialization rules
│       ├── case-file.md           # Specification of canonical case files
│       └── replay-report.md       # Specification of watcher replay reports
│
├── frontend/                      # Web interface (originally Developer 1)
│   ├── package.json               # Next.js 15, Wagmi, Viem, RainbowKit, Tailwind
│   ├── tsconfig.json              # Strict TypeScript settings with path aliases
│   ├── next.config.ts             # Next.js application configuration
│   ├── src/                       # Application source
│   │   ├── app/                   # App Router pages (markets, stress, claims, vault, feed)
│   │   ├── components/            # UI components (dashboard, claims, stress-testing, vault)
│   │   ├── hooks/                 # Web3 and data fetching hooks
│   │   ├── lib/                   # API clients, Viem hashing, formatting helpers
│   │   └── types/                 # TypeScript interfaces for API & contracts
│   └── tests/                     # Unit and component tests
│
├── core/                          # Pure calculation engine (originally Developer 2)
│   ├── pyproject.toml             # Package definition: stressproof-core
│   ├── README.md                  # Core library documentation
│   ├── src/stressproof_core/      # Source package
│   │   ├── __init__.py            # Library exports
│   │   ├── models.py              # Data structures (TypedDicts)
│   │   ├── constants.py           # Model IDs, basis points, domain bounds
│   │   ├── canonical_json.py      # Deterministic canonical byte serializer
│   │   ├── hashing.py             # Raw byte Keccak-256 and marketId computation
│   │   ├── validation.py          # Structural validation rules V-01..V-14
│   │   └── replay.py              # Pure integer static-liquidation-v1 engine
│   └── tests/                     # Property tests and Appendix A test vectors
│
├── pipeline/                      # Snapshot ingestion (originally Developer 2)
│   ├── pyproject.toml             # Package definition: stressproof-pipeline
│   ├── README.md                  # Aave v3 extraction guide
│   ├── src/stressproof_pipeline/  # Source package
│   │   ├── extraction/            # Borrower log discovery and Multicall3 classification
│   │   ├── normalization/         # Merge, canonicalize, synthetic generation, sweep
│   │   └── abis/                  # Minimal Aave v3 contract ABIs
│   └── tests/                     # Pipeline tests
│
├── backend/                       # FastAPI service (originally Developer 2)
│   ├── pyproject.toml             # Package definition: stressproof-backend
│   ├── README.md                  # Backend API documentation
│   ├── src/stressproof_backend/   # Source package
│   │   ├── main.py                # FastAPI entry point, CORS, routers
│   │   ├── config.py              # Pydantic Settings
│   │   ├── api/routes/            # REST routes (stress, files, datasets, feed, graph)
│   │   └── storage/               # Content-addressed file store (raw bytes)
│   └── tests/                     # API endpoint tests
│
├── agents/                        # Agents (originally Developer 3; Developer 2 as consumer)
│   ├── pyproject.toml             # Package definition: stressproof-agents
│   ├── README.md                  # Agent daemons documentation
│   ├── src/stressproof_agents/    # Source package
│   │   ├── common/                # Web3 connection, nonce management, SSRF fetcher
│   │   ├── attester/              # Honest attester publishing claims
│   │   ├── watcher/               # Continuous watcher detecting discrepancies & challenging
│   │   ├── resolver/              # Interactive Resolver CLI
│   │   └── malicious/             # Scripted malicious attester for demo
│   └── tests/                     # Agent execution tests
│
├── contracts/                     # Foundry smart contracts (originally Developer 3)
│   ├── foundry.toml               # Foundry configuration pinned to solc 0.8.24
│   ├── README.md                  # Contracts documentation
│   ├── src/                       # Solidity contracts (StressRegistry, DemoVault, MockLendingMarket)
│   ├── script/                    # Deployment scripts (Deploy.s.sol)
│   └── test/                      # Foundry test suites and Invariant tests
│
├── deployments/                   # Deployed addresses and constants
│   ├── 31337.json                 # Local Anvil deployment configuration
│   └── 84532.json                 # Base Sepolia deployment configuration
│
├── data/                          # Runtime data (gitignored except fixtures)
│   ├── fixtures/                  # Small golden fixtures committed for tests
│   ├── datasets/                  # Extracted Aave snapshots and manifests
│   ├── case-files/                # Content-addressed case file JSON files
│   └── replay-reports/            # Content-addressed watcher replay reports
│
└── scripts/                       # Orchestration and developer utility scripts
    ├── export_abis.sh             # Syncs compiled Foundry ABIs to frontend and agents
    ├── e2e_local.sh               # Automated Phase 1 gate verification on Anvil
    └── demo_testnet.sh            # Scripted testnet demo walkthrough
```
