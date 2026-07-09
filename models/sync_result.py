from dataclasses import dataclass

@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    files_embedded: int = 0
