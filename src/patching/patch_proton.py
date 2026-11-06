from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

try:
    from patching.i18n import t
except ImportError:
    from i18n import t

Log = Callable[[str], None]

STEAM = Path.home() / ".local/share/Steam"
STOCK_PROTON = STEAM / "steamapps/common/Proton - Experimental"
PATCHED_NAME = "Proton-Exp-MJLX"
PATCHED_PROTON = STEAM / "compatibilitytools.d" / PATCHED_NAME

OLD = bytes.fromhex("4c871424" "4153" "48812424ffbfffff" "9d" "48cf")
NEW = bytes.fromhex("4c89d1" "4c871424" "4153" "80642401bf" "9d" "48cf")
assert len(OLD) == len(NEW) == 17

VDF = f'''"compatibilitytools"
{{
  "compat_tools"
  {{
    "{PATCHED_NAME}"
    {{
      "install_path" "."
      "display_name" "Proton Experimental (MJLX RCX fix)"
      "from_oslist"  "windows"
      "to_oslist"    "linux"
    }}
  }}
}}
'''


class PatchError(Exception):
    pass


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
        raise PatchError(t("err.proton_missing"))
    so = find_ntdll(src)
    if so is None:
        raise PatchError(t("pp.err.no_ntdll_src"))
    count = so.read_bytes().count(OLD)
    if count != 1:
        raise PatchError(t("pp.err.pattern", count=count))


def create_patched_copy(src: Path = STOCK_PROTON, dst: Path = PATCHED_PROTON,
                        log: Log = print) -> None:
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
    (dst / "compatibilitytool.vdf").write_text(VDF)


def main() -> None:
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=STOCK_PROTON)
    ap.add_argument("--dst", type=Path, default=PATCHED_PROTON)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        if args.dry_run:
            check_source(args.src)
            print(t("pp.cli.dry"))
        else:
            create_patched_copy(args.src, args.dst)
            print(t("pp.cli.done1"))
            print(t("pp.cli.done2"))
    except PatchError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()