from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]

STATE = Path.home() / ".local/state/majesticrplinux"
MANGOHUD_DIR = STATE / "mangohud"
DXVK_LOG_DIR = STATE / "dxvk"

MANGOHUD_FIELDS = (
    "fps", "frametime", "frame_timing", "gpu_stats", "gpu_temp", "cpu_stats",
    "cpu_temp", "vram", "ram", "throttling_status",
)
DXVK_HUD_FIELDS = ("devinfo", "fps", "frametimes", "gpuload", "memory", "version", "api")
DXVK_OVERRIDES = "d3d11,d3d10core,d3d9,dxgi=n,b"
PRIME_ENV = {
    "__NV_PRIME_RENDER_OFFLOAD": "1",
    "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
    "__VK_LAYER_NV_optimus": "NVIDIA_only",
}
SHADER_CACHE_ENV = {
    "__GL_SHADER_DISK_CACHE": "1",
    "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP": "1",
    "__GL_SHADER_DISK_CACHE_SIZE": "10737418240",
}
SYNC_ENV = {"ntsync": "WINENTSYNC", "fsync": "WINEFSYNC", "esync": "WINEESYNC"}
MERGE_SEPARATORS = {"WINEDLLOVERRIDES": ";", "WINEDEBUG": ","}
ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

WATCHED_ENV = (
    "WINEDEBUG", "WINEDLLOVERRIDES", "WINEESYNC", "WINEFSYNC", "WINENTSYNC",
    "DXVK_HUD", "DXVK_FRAME_RATE", "DXVK_LOG_LEVEL", "MANGOHUD",
    "__NV_PRIME_RENDER_OFFLOAD", "__GLX_VENDOR_LIBRARY_NAME", "__VK_LAYER_NV_optimus",
    "LD_PRELOAD", "LC_ALL",
)
GRAPHICS_MODULES = (
    "d3d11.dll", "d3d10core.dll", "dxgi.dll", "d3d9.dll", "wined3d.dll",
    "winevulkan.dll", "vulkan-1.dll",
)
GAME_MARKERS = ("gta5", "playgtav")
MAX_GAME_PROCS = 3


@dataclass(frozen=True)
class Option:
    id: str
    kind: str
    group: str
    default: object = False
    choices: tuple = ()


OPTIONS = (
    Option("mangohud", "bool", "metrics"),
    Option("dxvk_hud", "bool", "metrics"),
    Option("fps_limit", "int", "metrics", 0),
    Option("loaddll", "bool", "logs"),
    Option("dxvk_log", "bool", "logs"),
    Option("winedebug_off", "bool", "logs"),
    Option("sync", "choice", "wine", "auto", ("auto", "ntsync", "fsync", "esync")),
    Option("force_dxvk", "bool", "wine"),
    Option("prime", "bool", "gpu"),
    Option("shader_cache", "bool", "gpu"),
    Option("gamemode", "bool", "process"),
)
GROUPS = ("metrics", "logs", "wine", "gpu", "process")


@dataclass
class Resolved:
    env: dict[str, str] = field(default_factory=dict)
    wrappers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _ensure(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _put(env: dict[str, str], key: str, value: str) -> None:
    sep = MERGE_SEPARATORS.get(key)
    if sep and env.get(key):
        env[key] = env[key] + sep + value
    else:
        env[key] = value


def resolve(values: dict, extra: str = "") -> Resolved:
    out = Resolved()
    env = out.env

    flags = []
    if values.get("winedebug_off"):
        flags.append("-all")
    if values.get("loaddll"):
        flags.append("+loaddll")
    if flags:
        env["WINEDEBUG"] = ",".join(flags)

    if values.get("mangohud"):
        _ensure(MANGOHUD_DIR)
        env["MANGOHUD"] = "1"
        env["MANGOHUD_CONFIG"] = ",".join(
            (*MANGOHUD_FIELDS, f"output_folder={MANGOHUD_DIR}", "autostart_log=5"))
        if shutil.which("mangohud") is None:
            out.notes.append("mangohud was not found in PATH, the overlay may not appear")

    if values.get("dxvk_hud"):
        env["DXVK_HUD"] = ",".join(DXVK_HUD_FIELDS)

    limit = int(values.get("fps_limit") or 0)
    if limit > 0:
        env["DXVK_FRAME_RATE"] = str(limit)

    if values.get("dxvk_log"):
        _ensure(DXVK_LOG_DIR)
        env["DXVK_LOG_LEVEL"] = "info"
        env["DXVK_LOG_PATH"] = str(DXVK_LOG_DIR)

    sync = values.get("sync", "auto")
    if sync in SYNC_ENV:
        env[SYNC_ENV[sync]] = "1"
        if sync == "ntsync" and not Path("/dev/ntsync").exists():
            out.notes.append("/dev/ntsync is missing, load the ntsync kernel module")

    if values.get("force_dxvk"):
        _put(env, "WINEDLLOVERRIDES", DXVK_OVERRIDES)

    if values.get("prime"):
        env.update(PRIME_ENV)

    if values.get("shader_cache"):
        env.update(SHADER_CACHE_ENV)

    if values.get("gamemode"):
        if shutil.which("gamemoderun"):
            out.wrappers.append("gamemoderun")
        else:
            out.notes.append("gamemoderun was not found in PATH, gamemode is skipped")

    for raw in extra.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not ENV_KEY.fullmatch(key):
            out.notes.append(f"ignored custom line: {line}")
            continue
        _put(env, key, value.strip().strip('"').strip("'"))

    return out


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _environ(pid: int) -> dict[str, str]:
    raw = _read(Path("/proc") / str(pid) / "environ")
    result: dict[str, str] = {}
    if raw is None:
        return result
    for item in raw.split(b"\0"):
        key, sep, value = item.partition(b"=")
        if sep:
            result[key.decode(errors="replace")] = value.decode(errors="replace")
    return result


def _game_processes(pfx: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return found
    for entry in entries:
        if not entry.name.isdigit():
            continue
        raw = _read(entry / "cmdline")
        if not raw:
            continue
        text = raw.replace(b"\0", b" ").decode(errors="replace").strip()
        low = text.lower()
        if not any(m in low for m in GAME_MARKERS) or "--type=" in low:
            continue
        if _environ(int(entry.name)).get("WINEPREFIX") != str(pfx):
            continue
        found.append((int(entry.name), text))
    return found[:MAX_GAME_PROCS]


def _graphics_modules(pid: int) -> list[str]:
    raw = _read(Path("/proc") / str(pid) / "maps")
    paths: set[str] = set()
    if raw is None:
        return []
    for line in raw.decode(errors="replace").splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        path = parts[5].replace(" (deleted)", "")
        if Path(path).name.lower() in GRAPHICS_MODULES:
            paths.add(path)
    return sorted(paths)


def _renderer_verdict(modules: list[str]) -> str:
    names = {Path(m).name.lower() for m in modules}
    d3d11 = [m for m in modules if Path(m).name.lower() == "d3d11.dll"]
    if any("drive_c" in m for m in d3d11):
        return "DXVK (d3d11.dll is loaded from the prefix)"
    if "wined3d.dll" in names:
        return "wined3d (OpenGL), DXVK is NOT used"
    if d3d11:
        return "d3d11.dll is loaded from Wine, renderer is unclear"
    return "no d3d11 module found yet, start the game first"


def _fd_counts(pid: int) -> dict[str, int]:
    counts = {"total": 0, "ntsync": 0, "eventfd": 0}
    try:
        fds = list((Path("/proc") / str(pid) / "fd").iterdir())
    except OSError:
        return counts
    for fd in fds:
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        counts["total"] += 1
        if "ntsync" in target:
            counts["ntsync"] += 1
        elif "eventfd" in target:
            counts["eventfd"] += 1
    return counts


def _status_fields(pid: int) -> str:
    raw = _read(Path("/proc") / str(pid) / "status")
    if raw is None:
        return "?"
    wanted = {}
    for line in raw.decode(errors="replace").splitlines():
        key, _, value = line.partition(":")
        if key in ("Threads", "VmRSS"):
            wanted[key] = value.strip()
    return ", ".join(f"{k}={v}" for k, v in wanted.items()) or "?"


def _run(cmd: list[str], env: dict | None, timeout: float = 8) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return ((r.stdout or "") + (r.stderr or "")).strip()


def _first_line(path: str) -> str | None:
    raw = _read(Path(path))
    if raw is None:
        return None
    return raw.decode(errors="replace").strip()


def _meminfo() -> dict[str, int]:
    raw = _read(Path("/proc/meminfo"))
    result: dict[str, int] = {}
    if raw is None:
        return result
    for line in raw.decode(errors="replace").splitlines():
        key, _, value = line.partition(":")
        digits = re.match(r"\s*(\d+)", value)
        if digits:
            result[key] = int(digits.group(1))
    return result


def _section(log: Log, title: str) -> None:
    log("")
    log(f"== {title} ==")


def _diagnose_game(pfx: Path, log: Log) -> None:
    _section(log, "Game processes")
    procs = _game_processes(pfx)
    if not procs:
        log("no GTA5.exe / PlayGTAV.exe process found in the prefix, start the game first")
        return
    for pid, cmd in procs:
        log(f"pid {pid}: {cmd[-100:]}")
        log(f"  {_status_fields(pid)}")
        env = _environ(pid)
        for key in WATCHED_ENV:
            log(f"  {key}={env.get(key, '(unset)')}")
        modules = _graphics_modules(pid)
        for module in modules:
            log(f"  module: {module}")
        log(f"  renderer: {_renderer_verdict(modules)}")
        counts = _fd_counts(pid)
        log(f"  fds: total={counts['total']} ntsync={counts['ntsync']} eventfd={counts['eventfd']}")
        if counts["ntsync"]:
            log("  sync: ntsync is active")
        elif counts["eventfd"] > 100:
            log("  sync: esync looks active")
        else:
            log("  sync: neither ntsync nor esync fds found (fsync or wineserver-based sync)")


def _diagnose_gpu(env: dict | None, log: Log) -> None:
    _section(log, "NVIDIA GPU")
    if shutil.which("nvidia-smi") is None:
        log("nvidia-smi was not found")
        return
    query = _run(["nvidia-smi", "--query-gpu=name,pstate,temperature.gpu,utilization.gpu,"
                  "clocks.sm,clocks.max.sm,power.draw,power.limit,memory.used,memory.total",
                  "--format=csv,noheader"], env)
    log(query or "nvidia-smi query failed")
    perf = _run(["nvidia-smi", "-q", "-d", "PERFORMANCE"], env)
    if perf:
        active = []
        for line in perf.splitlines():
            name, sep, value = line.partition(":")
            if sep and value.strip() == "Active":
                active.append(name.strip())
        log("active clock event reasons: " + (", ".join(active) if active else "none"))
    table = _run(["nvidia-smi"], env)
    if table:
        lines = [ln for ln in table.splitlines() if any(m in ln.lower() for m in GAME_MARKERS)]
        if lines:
            for ln in lines:
                log(ln.strip())
        else:
            log("the game is not listed among NVIDIA processes (it may be running on the iGPU)")


def _diagnose_system(env: dict | None, log: Log) -> None:
    _section(log, "System")
    log(f"/dev/ntsync: {'present' if Path('/dev/ntsync').exists() else 'missing'}")
    governor = _first_line("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    epp = _first_line("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")
    log(f"cpu governor: {governor or '?'}, energy preference: {epp or '?'}")
    if shutil.which("powerprofilesctl"):
        log(f"power profile: {_run(['powerprofilesctl', 'get'], env) or '?'}")
    for supply in sorted(Path("/sys/class/power_supply").glob("*")):
        if _first_line(str(supply / "type")) == "Mains":
            online = _first_line(str(supply / "online"))
            log(f"ac adapter {supply.name}: {'connected' if online == '1' else 'not connected'}")
    mem = _meminfo()
    if mem:
        swap_used = mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)
        log(f"ram: available {mem.get('MemAvailable', 0) // 1024} MiB of "
            f"{mem.get('MemTotal', 0) // 1024} MiB, swap used {swap_used // 1024} MiB")
    for tool in ("mangohud", "gamemoderun", "nvidia-smi"):
        log(f"{tool}: {shutil.which(tool) or 'not found'}")
    if shutil.which("gamemoded"):
        log(f"gamemode: {_run(['gamemoded', '-s'], env) or '?'}")


def diagnose(pfx: Path, log: Log, env: dict | None = None) -> None:
    log("Diagnostics started")
    _diagnose_game(pfx, log)
    _diagnose_gpu(env, log)
    _diagnose_system(env, log)
    log("")
    log("Diagnostics finished")
