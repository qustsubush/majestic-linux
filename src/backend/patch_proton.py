from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from i18n import t
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    from i18n import t

Log = Callable[[str], None]

STEAM = Path.home() / ".local/share/Steam"
COMMON = STEAM / "steamapps/common"
CUSTOM = STEAM / "compatibilitytools.d"
SUFFIX = "-MJLX"
DISPLAY_SUFFIX = " (MJLX RCX fix)"

STOCK_PROTON = COMMON / "Proton - Experimental"
PATCHED_NAME = "Proton-Exp-MJLX"
PATCHED_PROTON = CUSTOM / PATCHED_NAME
DEFAULT_LABEL = "Proton Experimental"

OLD = bytes.fromhex("4c871424" "4153" "48812424ffbfffff" "9d" "48cf")
NEW = bytes.fromhex("4c89d1" "4c871424" "4153" "80642401bf" "9d" "48cf")
assert len(OLD) == len(NEW) == 17


class PatchError(Exception):
    pass


@dataclass(frozen=True)
class Target:
    source: Path
    patched: Path
    name: str
    display: str


@dataclass(frozen=True)
class Source:
    id: str
    label: str


def make_vdf(name: str, display: str) -> str:
    return f'''"compatibilitytools"
{{
  "compat_tools"
  {{
    "{name}"
    {{
      "install_path" "."
      "display_name" "{display}"
      "from_oslist"  "windows"
      "to_oslist"    "linux"
    }}
  }}
}}
'''


def default_target() -> Target:
    return Target(STOCK_PROTON, PATCHED_PROTON, PATCHED_NAME, DEFAULT_LABEL + DISPLAY_SUFFIX)


def target_for(source_id: str = "") -> Target:
    kind, _, dirname = source_id.partition(":")
    if kind == "path" and dirname.startswith("/"):
        folder = Path(dirname.rstrip("/") or "/")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", folder.name).strip("-") or "Proton"
        name = f"{slug}{SUFFIX}"
        return Target(folder, CUSTOM / name, name, folder.name + DISPLAY_SUFFIX)
    if kind not in ("common", "custom") or dirname in ("", ".", "..") or "/" in dirname:
        return default_target()
    root = COMMON if kind == "common" else CUSTOM
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", dirname).strip("-")
    name = f"{slug}{SUFFIX}"
    return Target(root / dirname, CUSTOM / name, name, dirname + DISPLAY_SUFFIX)


def list_sources() -> list[Source]:
    found: list[Source] = []
    for kind, root in (("common", COMMON), ("custom", CUSTOM)):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not d.is_dir() or not (d / "proton").is_file():
                continue
            if d == STOCK_PROTON or d.name.endswith(SUFFIX):
                continue
            found.append(Source(f"{kind}:{d.name}", d.name))
    return found


def find_ntdll(root: Path) -> Path | None:
    return next(iter(sorted(root.glob("files/lib*/wine/x86_64-unix/ntdll.so"))), None)


def is_patched(root: Path = PATCHED_PROTON) -> bool:
    if not root.is_dir():
        return False
    so = find_ntdll(root)
    if so is None:
        return False
    try:
        data = so.read_bytes()
    except OSError:
        return False
    return NEW in data and OLD not in data


def check_source(src: Path = STOCK_PROTON) -> None:
    if not src.is_dir():
        raise PatchError(t("err.proton_missing", name=src.name))
    so = find_ntdll(src)
    if so is None:
        raise PatchError(t("pp.err.no_ntdll_src"))
    count = so.read_bytes().count(OLD)
    if count != 1:
        raise PatchError(t("pp.err.pattern", count=count))


def create_patched_copy(target: Target | None = None, log: Log = print) -> None:
    target = target or default_target()
    src, dst = target.source, target.patched
    if not dst.exists():
        check_source(src)
        log(t("pp.log.copy", name=src.name, dst=dst))
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(src, dst, symlinks=True)
        except Exception as e:
            shutil.rmtree(dst, ignore_errors=True)
            raise PatchError(t("pp.err.copy", err=e))

    so = find_ntdll(dst)
    if so is None:
        raise PatchError(t("pp.err.no_ntdll_dst"))
    data = so.read_bytes()
    if NEW in data and OLD not in data:
        log(t("pp.log.already"))
    else:
        count = data.count(OLD)
        if count != 1:
            raise PatchError(t("pp.err.pattern", count=count))
        mode = so.stat().st_mode
        so.chmod(mode | 0o200)
        so.write_bytes(data.replace(OLD, NEW, 1))
        so.chmod(mode)
        if NEW not in so.read_bytes():
            raise PatchError(t("pp.err.verify"))
        log(t("pp.log.patched"))
    (dst / "compatibilitytool.vdf").write_text(make_vdf(target.name, target.display))


def main() -> None:
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=STOCK_PROTON)
    ap.add_argument("--dst", type=Path, default=PATCHED_PROTON)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    target = Target(args.src, args.dst, args.dst.name, args.dst.name + DISPLAY_SUFFIX)
    try:
        if args.dry_run:
            check_source(args.src)
            print(t("pp.cli.dry"))
        else:
            create_patched_copy(target)
            print(t("pp.cli.done1"))
            print(t("pp.cli.done2"))
    except PatchError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()