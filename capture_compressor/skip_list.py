"""Files that did not get smaller, remembered so they are not retried on every start."""

from __future__ import annotations

import json

from .settings import application_directory

SKIP_LIST_FILE_NAME = "skipped.json"


class SkipList:
    def __init__(self) -> None:
        self.storage_file = application_directory() / SKIP_LIST_FILE_NAME
        try:
            stored = json.loads(self.storage_file.read_text(encoding="utf-8"))
            self.identities: set[str] = set(stored)
        except (OSError, ValueError):
            self.identities = set()

    def __contains__(self, identity: str) -> bool:
        return identity in self.identities

    def add(self, identity: str) -> None:
        self.identities.add(identity)
        self.storage_file.write_text(
            json.dumps(sorted(self.identities), indent=2), encoding="utf-8"
        )
