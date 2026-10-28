# ==============================================================================
# StressProof Monorepo Makefile
# Operational targets for Developers 1 (Frontend), 2 (Backend/Core), 3 (Blockchain/Agents)
# ==============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help setup test clean fork pin extract normalize sweep chain deploy-local deploy-testnet abis backend watcher attest evil resolve e2e web

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies across all domains (Python uv, Node pnpm)
	@echo "==> Setting up Python virtual environment and workspace packages..."
	uv sync
	@echo "==> Setting up Frontend dependencies..."
	cd frontend && pnpm install
	@echo "==> Setup completed successfully."

test: ## Run test suites across all domains (Forge, Pytest, Frontend)
	@echo "==> Running Foundry contract tests..."
	@if command -v forge &> /dev/null; then cd contracts && forge test; else echo "forge not installed or found in PATH; skipping contract tests"; fi
	@echo "==> Running Python workspace tests..."
	uv run pytest
	@echo "==> Running Frontend tests..."
	cd frontend && pnpm test

clean: ## Clean build artifacts, temporary caches, and logs
	rm -rf data/case-files/* data/replay-reports/* .pytest_cache contracts/out contracts/cache frontend/.next

# --- Pipeline Targets (Person B / Dev 2) ---

fork: ## Run local Anvil mainnet fork pinned at FORK_BLOCK
	@if [ -z "$$MAINNET_ARCHIVE_RPC_URL" ] || [ -z "$$FORK_BLOCK" ]; then \
		echo "ERROR: MAINNET_ARCHIVE_RPC_URL and FORK_BLOCK must be set in .env"; exit 1; \
	fi
	anvil --fork-url $$MAINNET_ARCHIVE_RPC_URL --fork-block-number $$FORK_BLOCK --port 8545

pin: ## Step 1: Pin Aave v3 Ethereum parameters at block N
	uv run -m stressproof_pipeline.extraction.pin

extract: ## Step 2: Discover and classify borrowers from Aave v3 fork
	uv run -m stressproof_pipeline.extraction.extract

synth: ## Step 3 (Optional): Generate synthetic accounts for testing
	uv run -m stressproof_pipeline.normalization.synth

normalize: ## Step 4: Merge, sort, canonicalize, and hash dataset snapshot
	uv run -m stressproof_pipeline.normalization.normalize

sweep: ## Step 4b: Run scenario sweep to identify non-zero bad debt R and select thresholds
	uv run -m stressproof_pipeline.normalization.sweep

# --- Blockchain & Contracts (Person A / Dev 3) ---

chain: ## Run standalone local Anvil testnet node on port 8546 for E2E testing
	anvil --port 8546

deploy-local: ## Deploy StressRegistry, DemoVault, MockLendingMarket to local Anvil
	cd contracts && forge script script/Deploy.s.sol:Deploy --rpc-url http://127.0.0.1:8546 --broadcast

deploy-testnet: ## Deploy contracts to Base Sepolia (or configured TESTNET_RPC_URL)
	cd contracts && forge script script/Deploy.s.sol:Deploy --rpc-url $$TESTNET_RPC_URL --broadcast --verify

abis: ## Export compiled contract ABIs to frontend and agent packages
	bash scripts/export_abis.sh

# --- Backend & Agent Run Targets ---

backend: ## Run FastAPI backend server
	uv run uvicorn stressproof_backend.main:app --host 0.0.0.0 --port 8000 --reload

watcher: ## Run the watcher agent polling loop
	uv run -m stressproof_agents.watcher.main

attest: ## Run honest attester agent to publish a claim
	uv run -m stressproof_agents.attester.main run --auto-finalize

evil: ## Run malicious attester demo script to publish an inflated claim
	uv run -m stressproof_agents.malicious.main

resolve: ## Run resolver CLI to resolve a disputed claim (usage: make resolve ID=1)
	@if [ -z "$(ID)" ]; then echo "ERROR: Provide ID, e.g., make resolve ID=1"; exit 1; fi
	uv run -m stressproof_agents.resolver.cli resolve $(ID)

# --- Frontend & Integration ---

web: ## Run Next.js frontend dev server
	cd frontend && pnpm dev

e2e: ## Run full automated end-to-end integration test with local Anvil
	bash scripts/e2e_local.sh
