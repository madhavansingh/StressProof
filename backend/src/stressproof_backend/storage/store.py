"""
Content-addressed raw byte storage.
Matches implementationplan.md §14 & §16.1.
"""

import os
import re
from pathlib import Path
from typing import Optional
from stressproof_core.hashing import keccak256_hex

HASH_REGEX = re.compile(r"^0x[0-9a-f]{64}$")


class ContentStore:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.case_files_dir = self.base_dir / "case-files"
        self.replay_reports_dir = self.base_dir / "replay-reports"

        self.case_files_dir.mkdir(parents=True, exist_ok=True)
        self.replay_reports_dir.mkdir(parents=True, exist_ok=True)

    def put_case_file(self, raw_bytes: bytes) -> str:
        """
        Stores canonical case file bytes addressed by keccak256 hash.
        """
        h = keccak256_hex(raw_bytes)
        dest = self.case_files_dir / f"{h}.json"
        if not dest.exists():
            tmp = self.case_files_dir / f"{h}.json.tmp"
            with open(tmp, "wb") as f:
                f.write(raw_bytes)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(dest)
        return h

    def get_case_file(self, h: str) -> Optional[bytes]:
        """
        Retrieves raw bytes for case file hash.
        """
        if not HASH_REGEX.match(h):
            return None
        target = self.case_files_dir / f"{h}.json"
        if not target.exists():
            return None
        with open(target, "rb") as f:
            return f.read()

    def put_replay_report(self, raw_bytes: bytes) -> str:
        """
        Stores canonical replay report bytes addressed by keccak256 hash.
        """
        h = keccak256_hex(raw_bytes)
        dest = self.replay_reports_dir / f"{h}.json"
        if not dest.exists():
            tmp = self.replay_reports_dir / f"{h}.json.tmp"
            with open(tmp, "wb") as f:
                f.write(raw_bytes)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(dest)
        return h

    def get_replay_report(self, h: str) -> Optional[bytes]:
        """
        Retrieves raw bytes for replay report hash.
        """
        if not HASH_REGEX.match(h):
            return None
        target = self.replay_reports_dir / f"{h}.json"
        if not target.exists():
            return None
        with open(target, "rb") as f:
            return f.read()
