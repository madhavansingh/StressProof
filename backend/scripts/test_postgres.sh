#!/usr/bin/env bash
# Run the backend test suite against a throwaway local PostgreSQL, then delete it.
#
#   bash backend/scripts/test_postgres.sh            # all backend tests on both storage backends
#   bash backend/scripts/test_postgres.sh -k feed    # extra arguments go to pytest
#
# Needs the PostgreSQL server tools (initdb, pg_ctl, createdb) on PATH, or PG_BIN pointing at
# their directory (Homebrew: brew install postgresql@16). The database lives in a fresh mktemp
# directory, listens only on 127.0.0.1 on a free port (TCP only, so long macOS temp paths cannot
# break the Unix socket), and is stopped and removed on exit, even when the tests fail.
# DATABASE_URL is cleared for the run: this script never touches the configured (Neon) database.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UV="${UV:-$(command -v uv || echo "$HOME/.local/bin/uv")}"

find_pg_bin() {
  if [ -n "${PG_BIN:-}" ]; then echo "$PG_BIN"; return; fi
  if command -v initdb >/dev/null 2>&1; then dirname "$(command -v initdb)"; return; fi
  for d in /opt/homebrew/opt/postgresql@*/bin /usr/local/opt/postgresql@*/bin /usr/lib/postgresql/*/bin; do
    if [ -x "$d/initdb" ]; then echo "$d"; return; fi
  done
  echo "error: PostgreSQL server tools not found; install them or set PG_BIN" >&2
  exit 2
}
PG_BIN="$(find_pg_bin)"
[ -x "$UV" ] || { echo "error: uv not found; install it or set UV" >&2; exit 2; }

export LC_ALL=C LANG=C   # initdb fails on some macOS locales without this
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/stressproof-pg.XXXXXX")"
PGDATA="$WORK_DIR/data"
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
STARTED=0
CLEANED=0

cleanup() {
  [ "$CLEANED" = 1 ] && return
  CLEANED=1
  if [ "$STARTED" = 1 ]; then
    # Covers a partial start too: pg_ctl may time out while the server is still coming up.
    "$PG_BIN/pg_ctl" -D "$PGDATA" -m immediate -w -t 15 stop >/dev/null 2>&1 || true
    if [ -f "$PGDATA/postmaster.pid" ]; then
      pid="$(head -1 "$PGDATA/postmaster.pid" 2>/dev/null || true)"
      case "$pid" in ''|*[!0-9]*) ;; *) kill -KILL "$pid" 2>/dev/null || true ;; esac
    fi
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

echo "==> throwaway PostgreSQL $("$PG_BIN/postgres" --version | awk '{print $3}') on 127.0.0.1:$PORT"
"$PG_BIN/initdb" -D "$PGDATA" -U stressproof --auth=trust -E UTF8 >"$WORK_DIR/initdb.log" 2>&1 \
  || { cat "$WORK_DIR/initdb.log" >&2; exit 2; }
STARTED=1   # set before starting, so cleanup also stops a server whose start timed out
"$PG_BIN/pg_ctl" -D "$PGDATA" -l "$WORK_DIR/server.log" -w -t 30 \
  -o "-p $PORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" start >/dev/null \
  || { cat "$WORK_DIR/server.log" >&2; exit 2; }
"$PG_BIN/createdb" -h 127.0.0.1 -p "$PORT" -U stressproof stressproof_test

echo "==> pytest backend/tests (filesystem + postgres)"
cd "$REPO_ROOT"
set +e
DATABASE_URL= TEST_DATABASE_URL="postgresql://stressproof@127.0.0.1:$PORT/stressproof_test" \
  "$UV" run --locked pytest backend/tests -q "$@"
status=$?
set -e
echo "==> removing throwaway PostgreSQL"
exit "$status"
