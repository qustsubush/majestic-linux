from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TextIO


def _open_paths(directory: Path) -> set[str]:
    prefix = str(directory) + os.sep
    found: set[str] = set()
    me = str(os.getpid())
    try:
        procs = list(Path("/proc").iterdir())
    except OSError:
        return found
    for proc in procs:
        if not proc.name.isdigit() or proc.name == me:
            continue
        try:
            fds = list(Path(proc, "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith(prefix):
                found.add(target)
    return found


class SessionLog:
    def __init__(self, directory: Path):
        self.dir = directory
        self.path: Path | None = None
        self._fh: TextIO | None = None

    def cleanup(self, extra: tuple[Path, ...] = ()) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        busy = _open_paths(self.dir)
        for f in self.dir.glob("*.log"):
            if str(f) in busy:
                continue
            f.unlink(missing_ok=True)
        for f in extra:
            f.unlink(missing_ok=True)

    def begin(self, prefix: str = "") -> Path:
        self.close()
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = self.dir / f"{prefix}{stamp}.log"
        self._fh = self.path.open("a", encoding="utf-8", buffering=1)
        return self.path

    def stream(self) -> TextIO:
        if self._fh is None:
            self.begin()
        return self._fh

    def write(self, line: str) -> None:
        if self._fh is None:
            self.begin()
        stamp = datetime.now().strftime("%H:%M:%S")
        self._fh.write(f"[{stamp}] {line}\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None