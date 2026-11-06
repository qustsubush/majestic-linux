from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from patching import patch_proton
from patching.i18n import t

Log = Callable[[str], None]

APP_ID = 271590
STEAM = Path.home() / ".local/share/Steam"
GTA_DIR = STEAM / "steamapps/common/Grand Theft Auto V"
COMPAT = STEAM / "steamapps/compatdata" / str(APP_ID)
PFX = COMPAT / "pfx"
STOCK_PROTON = patch_proton.STOCK_PROTON
PATCHED_PROTON = patch_proton.PATCHED_PROTON

SHORTCUT_NAME = "Majestic RP Linux"
SHORTCUT_ID = "majesticrplinux"

STATE = Path.home() / ".local/state/majesticrplinux"
SHIM_SO = STATE / "nolcall.so"
LOGS_DIR = STATE / "logs"
LEGACY_LOG = STATE / "launcher.log"

STEAM_BAT = PFX / "drive_c/majestic/steam-run.bat"
OLD_STEAM_BAT = PFX / "drive_c/steam-run.bat"
EMOJI_TTF = PFX / "drive_c/windows/Fonts/seguiemj.ttf"
EMOJI_FAMILY = "Segoe UI Emoji"
WINETRICKS_LOG = PFX / "winetricks.log"

CACHE = STATE / "cache"
SETUP_URL = "https://cdn.majestic-files.net/launcher/cis/MajesticLauncherSetup.exe"
EMOJI_URL = "https://github.com/mozilla/twemoji-colr/releases/download/v0.7.0/Twemoji.Mozilla.ttf"
EMOJI_SHA256 = "6d90152ee0d29e82fe2a87793af5aa4b7ad13e6538360889e141e81ed299ee8e"
EMOJI_SRC = CACHE / "Twemoji.Mozilla.ttf"
LAUNCHER_PROC = r"^[A-Za-z]:\\.*Majestic Launcher\.exe"

STEAM_BAT_TEXT = "\r\n".join([
    "@echo off",
    'set "GAMEARGS="',
    'for /f "tokens=4 delims=/" %%a in ("%~1") do set "GAMEARGS=%%a"',
    'cd /d "S:\\steamapps\\common\\Grand Theft Auto V"',
    'start "" PlayGTAV.exe %GAMEARGS%',
]) + "\r\n"
STEAM_CMD = r'C:\windows\system32\cmd.exe /c C:\majestic\steam-run.bat "%1"'

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

NOLCALL_C = r"""
#include <stdlib.h>
#include <string.h>
__attribute__((constructor))
static void nolcall_init(void) {
    const char *v = getenv("LC_ALL");
    if (v && strcmp(v, "C") == 0)
        unsetenv("LC_ALL");
}
"""

class SetupError(Exception):
    pass


@dataclass
class Config:
    installer: str = ""
    extra_args: str = ""


_current: subprocess.Popen | None = None
_cancel = threading.Event()

PACKAGE_MANAGERS = {
    "pacman": ("pacman", "-S", "--needed"),
    "apt": ("apt", "install"),
    "dnf": ("dnf", "install"),
    "zypper": ("zypper", "install"),
    "xbps-install": ("xbps-install", "-S"),
}


def _base_env() -> dict:
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig is not None:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def _run(cmd, log: Log, env=None, cwd=None, check=True) -> int:
    global _current
    log("$ " + " ".join(shlex.quote(str(c)) for c in cmd))
    if env is None:
        env = _base_env()
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd], env=env, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", start_new_session=True,
        )
    except FileNotFoundError:
        raise SetupError(t("err.cmd_not_found", cmd=cmd[0]))
    _current = proc
    try:
        for raw in proc.stdout:
            log(ANSI.sub("", raw.rstrip("\n")))
    finally:
        proc.wait()
        _current = None
    if check and proc.returncode != 0:
        raise SetupError(t("err.exit_code", name=Path(str(cmd[0])).name, code=proc.returncode))
    return proc.returncode


def stop(force: bool = False) -> None:
    _cancel.set()
    proc = _current
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass
    wineserver = _proton_dir() / "files/bin/wineserver"
    if wineserver.is_file():
        subprocess.run([str(wineserver), "-k"], env={**_base_env(), "WINEPREFIX": str(PFX)},
                       capture_output=True)


def _proton_dir() -> Path:
    if (PATCHED_PROTON / "proton").is_file() and is_proton_patched():
        return PATCHED_PROTON
    return STOCK_PROTON


def proton_bin() -> Path:
    p = _proton_dir() / "proton"
    if not p.is_file():
        raise SetupError(t("err.proton_missing"))
    return p


def _env(cfg: Config, preload: bool = False) -> dict:
    env = _base_env()
    env.update(
        STEAM_COMPAT_DATA_PATH=str(COMPAT),
        STEAM_COMPAT_CLIENT_INSTALL_PATH=str(STEAM),
        SteamAppId=str(APP_ID),
        SteamGameId=str(APP_ID),
    )
    if preload and SHIM_SO.is_file():
        old = env.get("LD_PRELOAD", "")
        env["LD_PRELOAD"] = f"{SHIM_SO}:{old}" if old else str(SHIM_SO)
    return env


def proton_run(args, cfg: Config, log: Log, **kw) -> int:
    return _run([proton_bin(), "run", *args], log, env=_env(cfg), **kw)


def detect_package_manager() -> str | None:
    return next((name for name in PACKAGE_MANAGERS if shutil.which(name)), None)


def install_command(pkgs: list[str]) -> str | None:
    pm = detect_package_manager()
    if pm is None:
        return None
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    return " ".join([*prefix, *PACKAGE_MANAGERS[pm], *pkgs])


def missing_packages(cfg: Config) -> list[str]:
    miss = []
    if not shutil.which("protontricks"):
        miss.append("protontricks")
    if not is_shim_built() and not shutil.which("gcc"):
        miss.append("gcc")
    return miss


def wait_for_packages(cfg: Config, log: Log, on_missing: Callable[[list[str], str, str], None],
                      poll: float = 2.0) -> None:
    shown: list[str] = []
    while True:
        missing = missing_packages(cfg)
        if not missing:
            if shown:
                on_missing([], "", "")
                log(t("gui.packages_ok"))
            return
        if missing != shown:
            shown = missing
            command = install_command(missing) or ""
            on_missing(missing, command, detect_package_manager() or "")
            log(t("gui.waiting_packages", pkgs=", ".join(missing)))
            if command:
                log("$ " + command)
        if _cancel.wait(poll):
            on_missing([], "", "")
            raise SetupError(t("err.cancelled"))


def find_launcher() -> Path | None:
    base = PFX / "drive_c/users/steamuser/AppData/Local"
    if not base.is_dir():
        return None
    return next(base.rglob("Majestic Launcher.exe"), None)


def kill_launcher() -> None:
    subprocess.run(["pkill", "-f", LAUNCHER_PROC], capture_output=True, env=_base_env())


def is_proton_patched() -> bool:
    return patch_proton.is_patched(PATCHED_PROTON)


def create_patched_proton(cfg: Config, log: Log) -> None:
    try:
        patch_proton.create_patched_copy(STOCK_PROTON, PATCHED_PROTON, log)
    except patch_proton.PatchError as e:
        raise SetupError(str(e))


def is_launcher_installed() -> bool:
    return find_launcher() is not None


def _download(url: str, dst: Path, log: Log) -> None:
    log(t("log.downloading", url=url))
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, tmp.open("wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(dst)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise SetupError(t("err.download", url=url, err=e))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _flush_registry() -> None:
    ws = _proton_dir() / "files/bin/wineserver"
    if not ws.is_file():
        return
    try:
        subprocess.run([str(ws), "-w"], env={**_base_env(), "WINEPREFIX": str(PFX)},
                       capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        pass


def _wait(cond: Callable[[], bool], seconds: int = 10) -> bool:
    for _ in range(seconds):
        if cond():
            return True
        time.sleep(1)
    return cond()


def is_powershell_installed() -> bool:
    try:
        lines = WINETRICKS_LOG.read_text(errors="ignore").splitlines()
    except OSError:
        return False
    return "powershell" in (ln.strip() for ln in lines)


def install_powershell(cfg: Config, log: Log) -> None:
    _run(["protontricks", str(APP_ID), "powershell"], log)
    if not is_powershell_installed():
        raise SetupError(t("err.powershell"))


def install_launcher(cfg: Config, log: Log) -> None:
    installer = Path(cfg.installer).expanduser() if cfg.installer else None
    if installer is None or not installer.is_file():
        installer = CACHE / "MajesticLauncherSetup.exe"
        _download(SETUP_URL, installer, log)
    _run(["protontricks-launch", "--appid", str(APP_ID), installer], log,
         env=_env(cfg))
    log(t("log.wait_install"))
    time.sleep(5)
    if not is_launcher_installed():
        raise SetupError(t("err.launcher_after_install"))


def is_steam_handler_patched() -> bool:
    try:
        reg = (PFX / "system.reg").read_text(errors="ignore")
    except OSError:
        return False
    return STEAM_BAT.is_file() and "majestic\\\\steam-run.bat" in reg


def patch_steam_handler(cfg: Config, log: Log) -> None:
    kill_launcher()
    STEAM_BAT.parent.mkdir(parents=True, exist_ok=True)
    STEAM_BAT.write_bytes(STEAM_BAT_TEXT.encode())
    OLD_STEAM_BAT.unlink(missing_ok=True)
    base = r"HKLM\Software\Classes\steam"
    proton_run(["reg", "add", base, "/ve", "/t", "REG_SZ", "/d", "URL:steam protocol", "/f"], cfg, log)
    proton_run(["reg", "add", base, "/v", "URL Protocol", "/t", "REG_SZ", "/d", "", "/f"], cfg, log)
    proton_run(["reg", "add", base + r"\shell\open\command", "/ve", "/t", "REG_SZ",
                "/d", STEAM_CMD, "/f"], cfg, log)
    _flush_registry()
    if not _wait(is_steam_handler_patched):
        raise SetupError(t("err.steam_handler"))


def is_shim_built() -> bool:
    return SHIM_SO.is_file()


def build_shim(cfg: Config, log: Log) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    src = STATE / "nolcall.c"
    src.write_text(NOLCALL_C)
    _run(["gcc", "-shared", "-fPIC", "-O2", "-o", SHIM_SO, src], log)


def is_emoji_installed() -> bool:
    try:
        reg = (PFX / "system.reg").read_text(errors="ignore").lower()
    except OSError:
        return False
    return EMOJI_TTF.is_file() and EMOJI_TTF.stat().st_size > 0 and "seguiemj.ttf" in reg


def _emoji_source(log: Log) -> Path:
    if EMOJI_SRC.is_file() and _sha256(EMOJI_SRC) == EMOJI_SHA256:
        return EMOJI_SRC
    EMOJI_SRC.unlink(missing_ok=True)
    _download(EMOJI_URL, EMOJI_SRC, log)
    if _sha256(EMOJI_SRC) != EMOJI_SHA256:
        EMOJI_SRC.unlink(missing_ok=True)
        raise SetupError(t("err.emoji_checksum"))
    return EMOJI_SRC


def rename_font(src: Path, dst: Path) -> None:
    from fontTools.ttLib import TTFont

    font = TTFont(str(src))
    names = font["name"]

    def put(name_id: int, text: str) -> None:
        names.removeNames(nameID=name_id)
        names.setName(text, name_id, 3, 1, 0x409)
        names.setName(text, name_id, 1, 0, 0)

    put(0, "Emoji artwork: Twemoji, Copyright Twitter, Inc and other contributors, CC-BY 4.0. "
           "Font: Mozilla twemoji-colr, Apache 2.0. Modified: family name changed.")
    put(1, "Segoe UI Emoji")
    put(2, "Regular")
    put(3, "Local rename of Twemoji Mozilla 0.7.0")
    put(4, "Segoe UI Emoji")
    put(6, "SegoeUIEmoji")
    put(13, "Emoji artwork licensed under CC-BY 4.0; font code under Apache License 2.0.")
    put(14, "https://creativecommons.org/licenses/by/4.0/")
    font.save(str(dst))


def install_emoji(cfg: Config, log: Log) -> None:
    src = _emoji_source(log)
    kill_launcher()
    EMOJI_TTF.parent.mkdir(parents=True, exist_ok=True)
    try:
        rename_font(src, EMOJI_TTF)
    except Exception as e:
        raise SetupError(t("err.font_rename", err=e))
    proton_run([
        "reg", "add", r"HKLM\Software\Microsoft\Windows NT\CurrentVersion\Fonts",
        "/v", f"{EMOJI_FAMILY} (TrueType)", "/t", "REG_SZ", "/d", EMOJI_TTF.name, "/f",
    ], cfg, log)
    _flush_registry()
    if not _wait(is_emoji_installed):
        raise SetupError(t("err.emoji_registry"))


@dataclass
class Step:
    title: str
    done: Callable[[], bool]
    run: Callable[[Config, Log], None]
    optional: bool = False


def steps(cfg: Config) -> list[Step]:
    return [
        Step(t("step.proton"), is_proton_patched, create_patched_proton),
        Step(t("step.powershell"), is_powershell_installed, install_powershell),
        Step(t("step.launcher"), is_launcher_installed, install_launcher),
        Step(t("step.handler"), is_steam_handler_patched, patch_steam_handler),
        Step(t("step.emoji"), is_emoji_installed, install_emoji, optional=True),
        Step(t("step.ru_fix"), is_shim_built, build_shim),
    ]


def required_done(cfg: Config) -> bool:
    return all(st.done() for st in steps(cfg) if not st.optional)


def is_installed(cfg: Config) -> bool:
    return not missing_packages(cfg) and required_done(cfg)


def install(cfg: Config, log: Log,
            on_step: Callable[[int, str], None] | None = None,
            on_missing: Callable[[list[str], str, str], None] | None = None) -> None:
    on_step = on_step or (lambda i, state: None)
    on_missing = on_missing or (lambda pkgs, command, manager: None)
    _cancel.clear()
    if not GTA_DIR.is_dir():
        raise SetupError(t("err.gta_missing"))
    if not PFX.is_dir():
        raise SetupError(t("err.no_prefix"))
    wait_for_packages(cfg, log, on_missing)
    for i, st in enumerate(steps(cfg)):
        if _cancel.is_set():
            raise SetupError(t("err.cancelled"))
        if st.done():
            on_step(i, "done")
            log(t("gui.step_done", title=st.title))
            continue
        on_step(i, "running")
        log(t("gui.step_run", title=st.title))
        try:
            st.run(cfg, log)
        except SetupError as e:
            if not st.optional:
                on_step(i, "error")
                raise
            on_step(i, "warn")
            log(t("gui.step_warn", title=st.title, err=e))
            continue
        on_step(i, "done")
    log(t("gui.install_done"))


def open_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(["xdg-open", str(LOGS_DIR)], env=_base_env(),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except FileNotFoundError:
        raise SetupError(t("err.cmd_not_found", cmd="xdg-open"))


DIAG_SKIP = (
    "wineserver", "services.exe", "winedevice.exe", "plugplay.exe", "svchost.exe",
    "explorer.exe", "rpcss.exe", "conhost.exe", "tabtip", "winemenubuilder",
    "preloader", "steam.exe",
)


def _inspect_proc(pid: int) -> tuple[str, str | None, bool] | None:
    base = Path("/proc") / str(pid)
    try:
        cmd = (base / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        env = (base / "environ").read_bytes().split(b"\0")
        maps = (base / "maps").read_text(errors="ignore")
    except OSError:
        return None
    if not any(e.startswith(b"WINEPREFIX=" + str(PFX).encode()) for e in env):
        return None
    low = cmd.lower()
    if not cmd or "--type=" in low or any(k in low for k in DIAG_SKIP):
        return None
    lc = next((e[7:].decode(errors="replace") for e in env if e.startswith(b"LC_ALL=")), None)
    return cmd, lc, SHIM_SO.name in maps


def _watch_shim(log: Log, stop_evt: threading.Event) -> None:
    seen: set[int] = set()
    while not stop_evt.wait(3):
        try:
            pids = [int(e.name) for e in Path("/proc").iterdir() if e.name.isdigit()]
        except OSError:
            continue
        for pid in pids:
            if pid in seen:
                continue
            info = _inspect_proc(pid)
            if info is None:
                continue
            seen.add(pid)
            cmd, lc, loaded = info
            log(t("diag.shim", pid=pid, name=cmd[-90:],
                  lc=lc if lc is not None else t("diag.unset"),
                  state=t("diag.loaded" if loaded else "diag.not_loaded")))


def launch(cfg: Config, log: Log) -> int:
    exe = find_launcher()
    if exe is None:
        raise SetupError(t("err.launcher_missing"))
    STATE.mkdir(parents=True, exist_ok=True)
    s_drive = PFX / "dosdevices/s:"
    try:
        if s_drive.is_symlink() or s_drive.exists():
            s_drive.unlink()
        s_drive.symlink_to(STEAM)
    except OSError as e:
        log(t("gui.drive_s_fail", err=e))
    cmd = ["protontricks-launch", "--appid", str(APP_ID), exe, *shlex.split(cfg.extra_args)]
    env = _env(cfg, preload=True)
    stop_evt = threading.Event()
    threading.Thread(target=_watch_shim, args=(log, stop_evt), daemon=True).start()
    try:
        return _run(cmd, log, env=env, cwd=exe.parent, check=False)
    finally:
        stop_evt.set()


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SetupError(t("err.not_png"))
    return struct.unpack(">II", head[16:24])


def _desktop_quote(arg: str) -> str:
    arg = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return '"' + arg.replace("%", "%%") + '"'


def create_shortcut(icon_png: Path, command: list[str]) -> Path:
    if not icon_png.is_file():
        raise SetupError(t("err.icon_missing", path=icon_png))
    w, h = _png_size(icon_png)
    size = f"{w}x{h}" if w == h else "256x256"
    share = Path.home() / ".local/share"
    icon_dst = share / "icons/hicolor" / size / "apps" / f"{SHORTCUT_ID}.png"
    icon_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(icon_png, icon_dst)

    apps = share / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    desktop = apps / f"{SHORTCUT_ID}.desktop"
    exec_line = " ".join(_desktop_quote(str(c)) for c in command)
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={SHORTCUT_NAME}\n"
        "Comment=Installation, patches and launch of the Majestic launcher on Linux\n"
        "Comment[ru]=Установка, патчи и запуск лаунчера Majestic на Linux\n"
        f"Exec={exec_line}\n"
        f"Icon={SHORTCUT_ID}\n"
        "Terminal=false\n"
        "Categories=Game;\n"
        f"StartupWMClass={SHORTCUT_ID}\n",
        encoding="utf-8",
    )
    desktop.chmod(0o755)
    for cmd in (["gtk-update-icon-cache", "-q", "-t", str(share / "icons/hicolor")],
                ["update-desktop-database", str(apps)]):
        try:
            subprocess.run(cmd, capture_output=True, env=_base_env())
        except FileNotFoundError:
            pass
    return desktop