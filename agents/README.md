# stressproof-agents

Autonomous agent daemons and CLIs for StressProof:
* `attester`: Runs stress-tests, publishes case files, and submits on-chain `postClaim`.
* `watcher`: Continuously watches `ClaimPosted` logs, fetches raw bytes, validates V-01..V-14, replays liquidation math, and issues challenges.
* `resolver`: Interactive Resolver CLI allowing the designated resolver to verify and resolve disputes.
* `malicious`: Scripted malicious attester producing inflated claims for testing dispute resolution.
