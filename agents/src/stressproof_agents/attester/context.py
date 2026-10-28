"""Builds everything an attester process needs from its environment, and checks it before use."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from ..common.chain import ChainClient
from ..common.config import AgentSettings, load_env_file, load_private_key
from ..common.deployments import Deployment, load_deployment
from ..common.feed import FeedClient
from ..common.fetch import EvidenceFetcher
from .backend import BackendClient


@dataclass(frozen=True)
class AttesterContext:
    settings: AgentSettings
    deployment: Deployment
    client: ChainClient
    backend: BackendClient
    fetcher: EvidenceFetcher
    feed: FeedClient


def read_env(env_file: Optional[Path]) -> Mapping[str, str]:
    """Process environment, overlaid with an env file when one is given or ./.env exists."""
    merged = dict(os.environ)
    path = env_file if env_file is not None else Path(".env")
    if env_file is not None or path.is_file():
        merged.update(load_env_file(path))
    return merged


def build_context(env: Mapping[str, str], role: str) -> AttesterContext:
    """Loads settings, the deployment and `role`'s key, connects, and verifies the deployment on chain."""
    settings = AgentSettings.from_env(env)
    deployment = load_deployment(settings.deployments_file)
    key = load_private_key(role, env)
    client = ChainClient.connect(settings.rpc_url_for(deployment.chain_id), deployment, key)
    client.verify_deployment()
    return AttesterContext(
        settings=settings,
        deployment=deployment,
        client=client,
        backend=BackendClient(settings.backend_url, settings.api_write_token),
        fetcher=EvidenceFetcher(settings.fetch),
        feed=FeedClient(settings.backend_url, settings.api_write_token),
    )
