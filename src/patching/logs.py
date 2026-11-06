from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TextIO


class SessionLog:
    def __init__(self, directory: Path):
        self.dir = directory
        self.path: Path | None = None
        self._fh: TextIO | None = None

    def cleanup(self, extra: tuple[Path, ...] = ()) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for f in self.dir.glob("*.log"):
            f.unlink(missing_ok=True)
        for f in extra:
            f.unlink(missing_ok=True)

    def begin(self, kind: str) -> Path:
        self.close()
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = self.dir / f"{stamp}_{kind}.log"
        self._fh = self.path.open("a", encoding="utf-8", buffering=1)
        return self.path

    def write(self, line: str) -> None:
        if self._fh is None:
            self.begin("app")
        stamp = datetime.now().strftime("%H:%M:%S")
        self._fh.write(f"[{stamp}] {line}\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
