"""
Minimal TigerGraph REST client (httpx, no extra dependency).

Endpoints (TigerGraph Savanna, HTTPS on 443):
- REST++ under /restpp: /requesttoken, /echo, /graph/<g> (upsert), /graph/<g>/vertices/<type>, /query/<g>/<q>.
- GSQL 4.x under /gsql/v1: /tokens (token from secret), /statements (run GSQL text).
Secrets are never logged or included in error messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

import httpx

TOKEN_LIFETIME_SEC = 86_400
GRAPH_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
QUERY_NAME = GRAPH_NAME


class TigerGraphError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class TigerGraphConfig:
    host: str
    graph: str
    secret: str = ""
    token: str = ""
    username: str = ""
    password: str = ""
    timeout: float = 15.0

    @staticmethod
    def from_settings(settings: Any) -> Optional["TigerGraphConfig"]:
        host = (settings.TG_HOST or "").strip().rstrip("/")
        if not host:
            return None
        return TigerGraphConfig(
            host=host, graph=settings.TG_GRAPH.strip(), secret=settings.TG_SECRET.get_secret_value(),
            token=settings.TG_TOKEN.get_secret_value(), username=settings.TG_USERNAME.strip(),
            password=settings.TG_PASSWORD.get_secret_value(), timeout=float(settings.TG_TIMEOUT_SEC),
        )

    def validate(self) -> None:
        url = urlparse(self.host)
        if url.scheme != "https" or not url.hostname or url.path not in ("", "/") or url.query:
            raise TigerGraphError("TG_HOST must be an https:// origin with no path, e.g. https://<id>.i.tgcloud.io")
        if not GRAPH_NAME.match(self.graph):
            raise TigerGraphError("TG_GRAPH must be a plain graph name")
        if not (self.secret or self.token):
            raise TigerGraphError("set TG_SECRET or TG_TOKEN")

    @property
    def public_host(self) -> str:
        return urlparse(self.host).hostname or ""


def _json(res: httpx.Response) -> Dict[str, Any]:
    try:
        body = res.json()
    except ValueError as exc:
        raise TigerGraphError(f"non-JSON reply (HTTP {res.status_code})", res.status_code) from exc
    if not isinstance(body, dict):
        raise TigerGraphError(f"unexpected reply shape (HTTP {res.status_code})", res.status_code)
    return body


def _error_text(body: Mapping[str, Any]) -> str:
    msg = body.get("message") or body.get("error") or "TigerGraph error"
    return str(msg)[:300]


class TigerGraphClient:
    def __init__(self, config: TigerGraphConfig, transport: Optional[httpx.BaseTransport] = None):
        config.validate()
        self.config = config
        self._token = config.token
        self._http = httpx.Client(base_url=config.host, timeout=config.timeout, transport=transport,
                                  follow_redirects=False, headers={"User-Agent": "stressproof-backend"})

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TigerGraphClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # --- auth ---------------------------------------------------------------------------------

    def token(self) -> str:
        """A REST++ token: TG_TOKEN if set, else one minted from TG_SECRET (4.x route, then 3.x route)."""
        if self._token:
            return self._token
        attempts = [
            ("/gsql/v1/tokens", {"secret": self.config.secret, "lifetime": TOKEN_LIFETIME_SEC}),
            ("/restpp/requesttoken", {"secret": self.config.secret, "lifetime": str(TOKEN_LIFETIME_SEC)}),
        ]
        failures = []
        for path, payload in attempts:
            try:
                res = self._http.post(path, json=payload)
            except httpx.HTTPError as exc:
                raise TigerGraphError(f"cannot reach TigerGraph: {type(exc).__name__}") from exc
            if res.status_code in (404, 405):
                failures.append(f"{path}: HTTP {res.status_code}")
                continue
            body = _json(res)
            token = body.get("token") or (body.get("results") or {}).get("token")
            if res.status_code == 200 and isinstance(token, str) and token:
                self._token = token
                return token
            failures.append(f"{path}: HTTP {res.status_code} {_error_text(body)}")
        raise TigerGraphError("could not get a token from TG_SECRET (" + "; ".join(failures) + ")", 401)

    def _auth(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            res = self._http.request(method, path, headers=self._auth(), **kwargs)
        except httpx.HTTPError as exc:
            raise TigerGraphError(f"cannot reach TigerGraph: {type(exc).__name__}") from exc
        body = _json(res)
        if res.status_code >= 400 or body.get("error") is True:
            raise TigerGraphError(f"{method} {path.split('?')[0]}: HTTP {res.status_code} {_error_text(body)}",
                                  res.status_code)
        return body

    # --- REST++ -------------------------------------------------------------------------------

    def echo(self) -> Dict[str, Any]:
        return self._request("GET", "/restpp/echo")

    def upsert(self, payload: Mapping[str, Any]) -> Dict[str, int]:
        body = self._request("POST", f"/restpp/graph/{self.config.graph}", json=payload,
                             params={"vertex_must_exist": "true"})
        result = (body.get("results") or [{}])[0]
        return {"accepted_vertices": int(result.get("accepted_vertices", 0)),
                "accepted_edges": int(result.get("accepted_edges", 0))}

    def vertices(self, vertex_type: str, where: Mapping[str, str], limit: int = 100_000) -> list:
        flt = ",".join(f'{k}="{v}"' for k, v in where.items())
        body = self._request("GET", f"/restpp/graph/{self.config.graph}/vertices/{vertex_type}",
                             params={"filter": flt, "limit": str(limit)})
        return list(body.get("results") or [])

    def run_query(self, name: str, params: Mapping[str, str]) -> list:
        if not QUERY_NAME.match(name):
            raise TigerGraphError("bad query name")
        body = self._request("GET", f"/restpp/query/{self.config.graph}/{name}", params=dict(params))
        return list(body.get("results") or [])

    # --- GSQL (setup only) ----------------------------------------------------------------------

    def gsql(self, statements: str) -> str:
        """Run GSQL text through the 4.x statements endpoint. Basic auth when TG_USERNAME is set."""
        if self.config.username:
            auth: Any = (self.config.username, self.config.password)
            headers = {"Content-Type": "text/plain"}
        else:
            auth, headers = None, {**self._auth(), "Content-Type": "text/plain"}
        try:
            res = self._http.post("/gsql/v1/statements", content=statements.encode("utf-8"),
                                  headers=headers, auth=auth, timeout=max(self.config.timeout, 600.0))
        except httpx.HTTPError as exc:
            raise TigerGraphError(f"cannot reach TigerGraph GSQL: {type(exc).__name__}") from exc
        if res.status_code >= 400:
            raise TigerGraphError(f"GSQL statements: HTTP {res.status_code} {res.text[:300]}", res.status_code)
        return res.text
