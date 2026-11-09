from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from i18n import t

STEAM = Path.home() / ".local/share/Steam"
CONFIG_VDF = STEAM / "config/config.vdf"
BACKUP_VDF = CONFIG_VDF.with_name("config.vdf.mjlx.bak")
COMPAT_PATH = ("InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping")
PRIORITY = "250"


class SteamConfigError(Exception):
    pass


@dataclass
class Tok:
    kind: str
    text: str
    start: int
    end: int


@dataclass
class Entry:
    key: Tok
    value: Tok | None
    children: list["Entry"] | None
    close: Tok | None


_TOKEN = re.compile(r'\s+|//[^\n]*|"((?:[^"\\]|\\.)*)"|([{}])')
_ESC = re.compile(r"\\(.)")
_UNESC = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


def _fail(detail: str) -> SteamConfigError:
    return SteamConfigError(t("err.steam_config", err=detail))


def _unescape(s: str) -> str:
    return _ESC.sub(lambda m: _UNESC.get(m.group(1), m.group(0)), s)


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise _fail(f"unexpected character at offset {pos}")
        if m.group(1) is not None:
            toks.append(Tok("s", _unescape(m.group(1)), m.start(), m.end()))
        elif m.group(2):
            toks.append(Tok(m.group(2), m.group(2), m.start(), m.end()))
        pos = m.end()
    return toks


def _parse(toks: list[Tok]) -> list[Entry]:
    pos = 0

    def entries(top: bool) -> tuple[list[Entry], Tok | None]:
        nonlocal pos
        items: list[Entry] = []
        while True:
            if pos >= len(toks):
                if top:
                    return items, None
                raise _fail("unexpected end of file")
            tok = toks[pos]
            if tok.kind == "}":
                if top:
                    raise _fail("unbalanced closing brace")
                pos += 1
                return items, tok
            if tok.kind != "s":
                raise _fail("unexpected opening brace")
            pos += 1
            if pos >= len(toks):
                raise _fail("unexpected end of file")
            nxt = toks[pos]
            pos += 1
            if nxt.kind == "{":
                sub, close = entries(False)
                items.append(Entry(tok, None, sub, close))
            elif nxt.kind == "s":
                items.append(Entry(tok, nxt, None, None))
            else:
                raise _fail("unexpected closing brace")

    items, _ = entries(True)
    return items


def _child(items: list[Entry], key: str) -> Entry | None:
    return next((e for e in items if e.children is not None and e.key.text == key), None)


def _value(items: list[Entry], key: str) -> Tok | None:
    return next((e.value for e in items if e.value is not None and e.key.text == key), None)


def _chain(items: list[Entry]) -> list[Entry]:
    chain: list[Entry] = []
    cur = items
    for key in COMPAT_PATH:
        node = _child(cur, key)
        if node is None:
            break
        chain.append(node)
        cur = node.children
    return chain


def _read() -> str:
    try:
        return CONFIG_VDF.read_text(encoding="utf-8")
    except OSError as e:
        raise _fail(str(e))


def compat_tool(appid: int) -> str | None:
    chain = _chain(_parse(_tokenize(_read())))
    if len(chain) < len(COMPAT_PATH):
        return None
    app = _child(chain[-1].children, str(appid))
    if app is None:
        return None
    name = _value(app.children, "name")
    return name.text if name else None


def _line_start(text: str, close: Tok) -> tuple[int, str]:
    start = text.rfind("\n", 0, close.start) + 1
    indent = text[start:close.start]
    if indent.strip():
        raise _fail("unexpected layout near a closing brace")
    return start, indent


def _app_text(appid: int, name: str, ind: str) -> str:
    return (
        f'{ind}"{appid}"\n{ind}{{\n'
        f'{ind}\t"name"\t\t"{_escape(name)}"\n'
        f'{ind}\t"config"\t\t""\n'
        f'{ind}\t"priority"\t\t"{PRIORITY}"\n'
        f"{ind}}}\n"
    )


def _apply(text: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, new in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + new + text[end:]
    return text


def set_compat_tool(appid: int, name: str) -> None:
    text = _read()
    chain = _chain(_parse(_tokenize(text)))
    edits: list[tuple[int, int, str]] = []
    if len(chain) == len(COMPAT_PATH):
        mapping = chain[-1]
        app = _child(mapping.children, str(appid))
        if app is None:
            start, ind = _line_start(text, mapping.close)
            edits.append((start, start, _app_text(appid, name, ind + "\t")))
        else:
            current = _value(app.children, "name")
            if current is not None:
                edits.append((current.start, current.end, f'"{_escape(name)}"'))
            else:
                start, ind = _line_start(text, app.close)
                edits.append((start, start, f'{ind}\t"name"\t\t"{_escape(name)}"\n'))
    else:
        if len(chain) < len(COMPAT_PATH) - 1:
            raise _fail("Steam section not found in config.vdf")
        steam = chain[-1]
        start, ind = _line_start(text, steam.close)
        inner = ind + "\t"
        block = (
            f'{inner}"{COMPAT_PATH[-1]}"\n{inner}{{\n'
            f"{_app_text(appid, name, inner + chr(9))}"
            f"{inner}}}\n"
        )
        edits.append((start, start, block))
    new_text = _apply(text, edits)
    _parse(_tokenize(new_text))
    if not BACKUP_VDF.exists():
        shutil.copy2(CONFIG_VDF, BACKUP_VDF)
    tmp = CONFIG_VDF.with_name(CONFIG_VDF.name + ".mjlx.tmp")
    try:
        tmp.write_text(new_text, encoding="utf-8")
        shutil.copymode(CONFIG_VDF, tmp)
        tmp.replace(CONFIG_VDF)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise _fail(str(e))
    if compat_tool(appid) != name:
        shutil.copy2(BACKUP_VDF, CONFIG_VDF)
        raise _fail("verification failed, config restored from backup")


def steam_running() -> bool:
    try:
        r = subprocess.run(["pgrep", "-x", "steam"], capture_output=True)
    except FileNotFoundError:
        return False
    return r.returncode == 0