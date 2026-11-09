#!/usr/bin/env python3
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QPointF, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl,
    QObject, QVariantAnimation, Signal, Slot,
)
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QPainter, QPalette, QPen, QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QPlainTextEdit,
    QMessageBox, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

SRC_DIR = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", SRC_DIR))
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.services.warning=false")

import backend.patch as core
import i18n
from backend import logs, patch_proton
from i18n import t

APP_VERSION = "2.1.0"
APP_ID = "majestic-linux"
DESKTOP_ID = "majesticrplinux"
GITHUB_URL = "https://github.com/qustsubush/majestic-linux"
ICON_PATH = RES_DIR / "assets" / "icon.svg"
ICON_PNG = RES_DIR / "assets" / "icon.png"
WIN_W, WIN_H = 860, 580
DEFAULT_ARGS = "-disable-gpu"

ACCENT = "#4a7fb5"
OK_COLOR, BAD_COLOR, WARN_COLOR = "#6fb06f", "#c96a6a", "#c9a24a"

STYLE = f"""
QPushButton {{
    background: #2b2b2b; border: 1px solid #3c3c3c; border-radius: 3px; padding: 6px 12px;
}}
QPushButton:hover {{ background: #333333; }}
QPushButton:pressed {{ background: #262626; }}
QPushButton:disabled {{ color: #777777; }}
QPushButton#iconBtn {{ padding: 0; }}
QPushButton#play {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: white;
    font-weight: bold; padding: 10px;
}}
QPushButton#play:hover {{ background: #5a8fc5; }}
QPushButton#play:disabled {{ background: #333333; border-color: #3c3c3c; color: #777777; }}
QPushButton#play[running="true"] {{ background: #a54b4b; border-color: #a54b4b; }}
QPushButton#play[big="true"] {{ font-size: 20px; }}
QComboBox QAbstractItemView {{ background: #1b1b1b; selection-background-color: #2e2e2e; outline: 0; }}
#panel {{ background: #1b1b1b; border: 1px solid #3c3c3c; border-radius: 3px; }}
QListWidget {{ background: #1b1b1b; border: none; outline: 0; }}
QListWidget::item {{ padding: 9px 12px; }}
QListWidget::item:selected {{ background: #2e2e2e; color: white; }}
QListWidget::item:hover {{ background: #262626; }}
QLineEdit, QPlainTextEdit {{
    background: #1b1b1b; border: 1px solid #3c3c3c; border-radius: 3px; padding: 5px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
#row {{ border-bottom: 1px solid #333333; }}
#muted {{ color: #8a8a8a; }}
#pageTitle {{ font-size: 16px; font-weight: bold; }}
"""


def apply_dark_palette(app: QApplication) -> None:
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#232323"))
    p.setColor(QPalette.WindowText, QColor("#e0e0e0"))
    p.setColor(QPalette.Base, QColor("#1b1b1b"))
    p.setColor(QPalette.Text, QColor("#e0e0e0"))
    p.setColor(QPalette.Button, QColor("#2b2b2b"))
    p.setColor(QPalette.ButtonText, QColor("#e0e0e0"))
    p.setColor(QPalette.Highlight, QColor(ACCENT))
    p.setColor(QPalette.HighlightedText, QColor("white"))
    p.setColor(QPalette.PlaceholderText, QColor("#777777"))
    app.setPalette(p)


def open_logs():
    try:
        core.open_logs_dir()
    except core.SetupError as e:
        QMessageBox.warning(None, "Majestic Linux", str(e))


def load_config(s: QSettings) -> core.Config:
    cfg = core.Config(
        extra_args=str(s.value("extra_args", DEFAULT_ARGS)),
        proton=str(s.value("proton", "")),
    )
    core.use_config(cfg)
    return cfg


class LangSwitch(QAbstractButton):
    def __init__(self, checked: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(72, 26)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)

    def _set_pos(self, value):
        self._pos = float(value)
        self.update()

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor("#3c3c3c"), 1))
        p.setBrush(QColor("#2b2b2b"))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), h / 2, h / 2)
        half = (w - 6) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(QRectF(3 + half * self._pos, 3, half, h - 6), (h - 6) / 2, (h - 6) / 2)
        font = self.font()
        font.setBold(True)
        p.setFont(font)
        for i, text in enumerate(("EN", "RU")):
            cell = QRectF(3 + half * i, 3, half, h - 6)
            active = abs(self._pos - i) < 0.5
            p.setPen(QColor("white" if active else "#8a8a8a"))
            p.drawText(cell, Qt.AlignCenter, text)


def _mix(a: str, b: str, k: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * k),
        round(ca.green() + (cb.green() - ca.green()) * k),
        round(ca.blue() + (cb.blue() - ca.blue()) * k),
    )


class ToggleSwitch(LangSwitch):
    def __init__(self, checked: bool = False):
        super().__init__(checked)
        self.setFixedSize(44, 24)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor("#3c3c3c"), 1))
        p.setBrush(_mix("#2b2b2b", ACCENT, self._pos))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), h / 2, h / 2)
        d = h - 6
        x = 3 + (w - 6 - d) * self._pos
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white" if self.isChecked() else "#8a8a8a"))
        p.drawEllipse(QRectF(x, 3, d, d))


def reset_icon() -> QIcon:
    icon = QIcon()
    scale = 2
    for mode, color in ((QIcon.Normal, "#e0e0e0"), (QIcon.Disabled, "#5a5a5a")):
        pm = QPixmap(16 * scale, 16 * scale)
        pm.fill(Qt.transparent)
        pm.setDevicePixelRatio(scale)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(color), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        cx, cy, r = 8.0, 8.0, 5.5
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 30 * 16, 300 * 16)
        theta = math.radians(330)
        end = QPointF(cx + r * math.cos(theta), cy - r * math.sin(theta))
        d = QPointF(-math.sin(theta), -math.cos(theta))
        n = QPointF(-d.y(), d.x())
        tip = end + d * 2.6
        base = end - d * 0.8
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([tip, base + n * 2.8, base - n * 2.8]))
        p.end()
        icon.addPixmap(pm, mode)
    return icon


class SettingRow(QFrame):
    def __init__(self, widget: QWidget):
        super().__init__()
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel()
        self.desc = QLabel()
        self.desc.setObjectName("muted")
        self.desc.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.desc)
        lay.addLayout(texts, 1)
        lay.addWidget(widget, 0, Qt.AlignVCenter)

    def set_texts(self, title: str, desc: str):
        self.title.setText(title)
        self.desc.setText(desc)


class SettingRow(QFrame):
    def __init__(self, widget: QWidget):
        super().__init__()
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel()
        self.desc = QLabel()
        self.desc.setObjectName("muted")
        self.desc.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.desc)
        lay.addLayout(texts, 1)
        lay.addWidget(widget, 0, Qt.AlignVCenter)

    def set_texts(self, title: str, desc: str):
        self.title.setText(title)
        self.desc.setText(desc)


class ArgsEditor(QWidget):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edit = QLineEdit(str(settings.value("extra_args", DEFAULT_ARGS)))
        self.edit.setMinimumWidth(220)
        self.edit.editingFinished.connect(self.save)
        self.edit.textChanged.connect(self.update_reset)
        self.reset_btn = QPushButton()
        self.reset_btn.setObjectName("iconBtn")
        self.reset_btn.setIcon(reset_icon())
        self.reset_btn.setIconSize(QSize(16, 16))
        self.reset_btn.setFixedSize(30, 30)
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self.reset)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.reset_btn)
        self.update_reset()

    def save(self):
        self.settings.setValue("extra_args", self.edit.text())

    def update_reset(self):
        self.reset_btn.setEnabled(self.edit.text() != DEFAULT_ARGS)

    def reset(self):
        self.edit.setText(DEFAULT_ARGS)
        self.save()

    def retranslate(self):
        self.edit.setPlaceholderText(t("settings.args.placeholder"))
        self.reset_btn.setToolTip(t("settings.args.reset"))


class ProtonPicker(QComboBox):
    changed = Signal()
    BROWSE = "__browse__"

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.setMinimumWidth(260)
        self.populate()
        self.activated.connect(self._on_activated)

    def populate(self):
        current = str(self.settings.value("proton", ""))
        self.blockSignals(True)
        self.clear()
        self.addItem(t("settings.proton.default"), "")
        for src in patch_proton.list_sources():
            self.addItem(src.label, src.id)
        index = self.findData(current)
        if index < 0:
            self.addItem(current.partition(":")[2] or current, current)
            index = self.count() - 1
        self.addItem(t("settings.proton.browse"), self.BROWSE)
        self.setCurrentIndex(index)
        self.blockSignals(False)

    def showPopup(self):
        self.populate()
        super().showPopup()

    def _on_activated(self, index: int):
        value = str(self.itemData(index))
        if value == self.BROWSE:
            start = str(Path.home() / ".local/share/Steam")
            chosen = QFileDialog.getExistingDirectory(self, t("settings.proton.pick"), start)
            if not chosen:
                self.populate()
                return
            if not (Path(chosen) / "proton").is_file():
                QMessageBox.warning(self, "Majestic Linux", t("settings.proton.invalid"))
                self.populate()
                return
            value = f"path:{chosen}"
        if value == str(self.settings.value("proton", "")):
            self.populate()
            return
        self.settings.setValue("proton", value)
        self.populate()
        self.changed.emit()

    def retranslate(self):
        self.populate()


class LogBus(QObject):
    line = Signal(str)

    def __init__(self, prefix: str = ""):
        super().__init__()
        self.prefix = prefix
        self.session = logs.SessionLog(core.LOGS_DIR)

    def begin(self):
        path = self.session.begin(self.prefix)
        self.push(t("gui.log_file", path=path))

    @Slot(str)
    def push(self, text: str):
        self.session.write(text)
        self.line.emit(text)

    def close(self):
        self.session.close()


def new_log_view() -> QPlainTextEdit:
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setMaximumBlockCount(5000)
    view.setFont(QFont("monospace", 9))
    return view


class Worker(QThread):
    line = Signal(str)
    step = Signal(int, str)
    packages = Signal(list, str, str)
    finished_with = Signal(object)

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self):
        code = 1
        try:
            code = self.job(self)
        except core.SetupError as e:
            self.line.emit(t("gui.error", err=e))
        except Exception as e:
            self.line.emit(t("gui.unexpected", err=repr(e)))
        self.finished_with.emit(code)


_debug_windows: list = []


class DebugWindow(QWidget):
    def __init__(self, cfg: core.Config):
        super().__init__()
        self.cfg = cfg
        self.bus = LogBus()
        self.worker: Worker | None = None
        self.setWindowTitle(t("debug.title"))
        self.resize(780, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        self.view = new_log_view()
        self.view.setPlaceholderText(t("log.placeholder"))
        self.bus.line.connect(self.view.appendPlainText)
        root.addWidget(self.view, 1)

        bar = QHBoxLayout()
        self.stop_btn = QPushButton(t("debug.stop_prefix"))
        self.stop_btn.clicked.connect(self.stop_prefix)
        self.copy_btn = QPushButton(t("btn.copy_log"))
        self.copy_btn.clicked.connect(self.copy_log)
        self.logs_btn = QPushButton(t("btn.open_logs"))
        self.logs_btn.clicked.connect(open_logs)
        self.status = QLabel(t("status.running"))
        self.status.setObjectName("muted")
        bar.addWidget(self.stop_btn)
        bar.addWidget(self.copy_btn)
        bar.addWidget(self.logs_btn)
        bar.addStretch(1)
        bar.addWidget(self.status)
        root.addLayout(bar)

    def start(self):
        cfg = self.cfg

        def job(w: Worker):
            w.line.emit(t("gui.launching"))
            return core.launch(cfg, w.line.emit)

        self.bus.begin()
        self.worker = Worker(job)
        self.worker.line.connect(self.bus.push)
        self.worker.finished_with.connect(self._on_finished)
        self.worker.start()

    def _running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def stop_prefix(self):
        if not self._running():
            return
        self.stop_btn.setEnabled(False)
        self.status.setText(t("status.stopping"))
        core.stop()
        QTimer.singleShot(3000, self._force_stop)

    def _force_stop(self):
        if self._running():
            core.stop(force=True)

    def copy_log(self):
        QApplication.clipboard().setText(self.view.toPlainText())
        self.status.setText(t("status.log_copied"))

    def _on_finished(self, code):
        self.bus.push(t("gui.finished", code=code))
        self.stop_btn.setEnabled(False)
        self.status.setText(t("debug.finished"))

    def closeEvent(self, event):
        if self._running():
            answer = QMessageBox.question(self, t("debug.title"), t("debug.confirm_close"))
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            core.stop(force=True)
            self.worker.wait(3000)
        self.bus.close()
        if self in _debug_windows:
            _debug_windows.remove(self)
        super().closeEvent(event)


class GeneralPage(QWidget):
    running_changed = Signal(bool)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.bus = LogBus()
        self.worker: Worker | None = None
        self._busy = False
        self._locked = False
        self._fail_code = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 14, 14)
        root.setSpacing(10)

        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        root.addWidget(self.title)

        self.play = QPushButton()
        self.play.setObjectName("play")
        self.play.setProperty("big", True)
        self.play.setCursor(Qt.PointingHandCursor)
        self.play.setFixedSize(300, 80)
        self.play.clicked.connect(self.start)

        self.logs_btn = QPushButton()
        self.logs_btn.setFixedSize(300, 32)
        self.logs_btn.clicked.connect(open_logs)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setAlignment(Qt.AlignCenter)
        self.note.setStyleSheet(f"color: {WARN_COLOR};")

        root.addStretch(1)
        root.addWidget(self.play, 0, Qt.AlignHCenter)
        root.addWidget(self.logs_btn, 0, Qt.AlignHCenter)
        root.addSpacing(6)
        root.addWidget(self.note)
        root.addStretch(1)

        self.retranslate()

    def retranslate(self):
        self.title.setText(t("nav.general"))
        self.play.setText(t("status.starting" if self._busy else "btn.play"))
        self.logs_btn.setText(t("btn.open_logs"))
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def set_locked(self, locked: bool):
        self._locked = locked
        self.refresh()

    def refresh(self):
        installed = core.is_installed(load_config(self.settings))
        if not installed:
            self.note.setText(t("general.not_installed"))
        elif self._fail_code is not None:
            self.note.setText(t("gui.launch_failed", code=self._fail_code))
        self.note.setVisible(not installed or self._fail_code is not None)
        self.play.setEnabled(installed and not self._locked and not self._busy)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.play.setText(t("status.starting" if busy else "btn.play"))
        self.running_changed.emit(busy)
        self.refresh()

    def start(self):
        cfg = load_config(self.settings)
        if not core.is_installed(cfg):
            self.refresh()
            return
        self._fail_code = None
        if self.settings.value("debug", False, type=bool):
            self._start_debug(cfg)
        else:
            self._start_plain(cfg)

    def _start_debug(self, cfg: core.Config):
        win = DebugWindow(cfg)
        _debug_windows.append(win)
        win.show()
        win.start()
        self.window().close()

    def _start_plain(self, cfg: core.Config):
        self.bus.begin()
        stream = self.bus.session.stream()

        def job(w: Worker):
            w.line.emit(t("gui.launching"))
            return core.launch(cfg, w.line.emit, detach_out=stream)

        self.worker = Worker(job)
        self.worker.line.connect(self.bus.push)
        self.worker.finished_with.connect(self._on_finished)
        self._set_busy(True)
        self.worker.start()

    def _on_finished(self, code):
        self.worker.wait()
        if code is None:
            self.window().close()
            return
        self.bus.push(t("gui.finished", code=code))
        self._fail_code = code
        self._set_busy(False)


class InstallPage(QWidget):
    running_changed = Signal(bool)

    GLYPHS = {
        "pending": ("○", "#8a8a8a"),
        "running": ("▸", ACCENT),
        "done": ("✓", OK_COLOR),
        "warn": ("!", WARN_COLOR),
        "error": ("✗", BAD_COLOR),
    }

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.bus = LogBus("install-")
        self.worker: Worker | None = None
        self._running = False
        self._stopping = False
        self._status_key = "install.status.idle"
        self._states: list[str] = []
        self._titles: list[str] = []
        self._packages: tuple[list[str], str, str] = ([], "", "")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 14, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.status = QLabel()
        self.status.setObjectName("muted")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.status)
        root.addLayout(head)

        self.desc = QLabel()
        self.desc.setObjectName("muted")
        self.desc.setWordWrap(True)
        root.addWidget(self.desc)

        self.steps_box = QVBoxLayout()
        self.steps_box.setSpacing(2)
        root.addLayout(self.steps_box)
        self.step_labels: list[QLabel] = []

        self.panel = QFrame()
        self.panel.setObjectName("panel")
        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(10, 8, 10, 10)
        panel_lay.setSpacing(6)
        self.panel_title = QLabel()
        self.panel_title.setStyleSheet("font-weight: bold;")
        self.panel_desc = QLabel()
        self.panel_desc.setObjectName("muted")
        self.panel_desc.setWordWrap(True)
        cmd_row = QHBoxLayout()
        self.cmd = QLineEdit()
        self.cmd.setReadOnly(True)
        self.cmd.setFont(QFont("monospace", 9))
        self.cmd_copy = QPushButton()
        self.cmd_copy.clicked.connect(self.copy_command)
        cmd_row.addWidget(self.cmd, 1)
        cmd_row.addWidget(self.cmd_copy)
        panel_lay.addWidget(self.panel_title)
        panel_lay.addWidget(self.panel_desc)
        panel_lay.addLayout(cmd_row)
        self.panel.hide()
        root.addWidget(self.panel)

        self.action = QPushButton()
        self.action.setObjectName("play")
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self.toggle)
        root.addWidget(self.action)

        self.log = new_log_view()
        self.bus.line.connect(self.log.appendPlainText)
        root.addWidget(self.log, 1)

        bar = QHBoxLayout()
        self.copy_log_btn = QPushButton()
        self.copy_log_btn.clicked.connect(self.copy_log)
        self.logs_btn = QPushButton()
        self.logs_btn.clicked.connect(open_logs)
        bar.addWidget(self.copy_log_btn)
        bar.addWidget(self.logs_btn)
        bar.addStretch(1)
        root.addLayout(bar)

        self.retranslate()

    def copy_log(self):
        QApplication.clipboard().setText(self.log.toPlainText())
        self.status.setText(t("status.log_copied"))
        QTimer.singleShot(2000, lambda: self.status.setText(t(self._status_key)))

    def retranslate(self):
        self.title.setText(t("nav.install"))
        self.copy_log_btn.setText(t("btn.copy_log"))
        self.logs_btn.setText(t("btn.open_logs"))
        self.desc.setText(t("install.desc"))
        self.cmd_copy.setText(t("btn.copy"))
        self.log.setPlaceholderText(t("log.placeholder"))
        self.action.setText(t("btn.stop" if self._running else "btn.install"))
        self.status.setText(t(self._status_key))
        self._render_packages()
        self.refresh()

    def _set_status(self, key: str):
        self._status_key = key
        self.status.setText(t(key))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def set_locked(self, locked: bool):
        self.action.setEnabled(not locked and self._needs_install())

    def _needs_install(self) -> bool:
        return not core.is_installed(load_config(self.settings))

    def refresh(self):
        if self._running:
            return
        cfg = load_config(self.settings)
        items = core.steps(cfg)
        old_titles, old_states = self._titles, self._states
        self._titles = [st.title for st in items]
        states = []
        for i, st in enumerate(items):
            if st.done():
                states.append("done")
            elif i < len(old_states) and old_states[i] in ("warn", "error") \
                    and old_titles[i] == st.title:
                states.append(old_states[i])
            else:
                states.append("pending")
        self._states = states
        self._render_steps()
        complete = core.is_installed(cfg)
        self.action.setEnabled(not complete)
        if complete:
            self._set_status("install.status.done")
        elif self._status_key == "install.status.done":
            self._set_status("install.status.idle")

    def _render_steps(self):
        while len(self.step_labels) < len(self._titles):
            lab = QLabel()
            self.step_labels.append(lab)
            self.steps_box.addWidget(lab)
        for i, lab in enumerate(self.step_labels):
            if i >= len(self._titles):
                lab.hide()
                continue
            lab.show()
            glyph, color = self.GLYPHS[self._states[i]]
            lab.setText(f'<span style="color:{color}">{glyph}</span>&nbsp;&nbsp;{self._titles[i]}')

    def _render_packages(self):
        pkgs, command, manager = self._packages
        if not pkgs:
            self.panel.hide()
            return
        self.panel_title.setText(t("install.packages.title"))
        if manager and command:
            self.panel_desc.setText(t("install.packages.desc", pm=manager))
        else:
            self.panel_desc.setText(t("install.packages.unknown"))
        self.cmd.setText(command or " ".join(pkgs))
        self.cmd.setCursorPosition(0)
        self.panel.show()

    def copy_command(self):
        QApplication.clipboard().setText(self.cmd.text())
        self.status.setText(t("status.cmd_copied"))

    def on_step(self, index: int, state: str):
        if index < len(self._states):
            self._states[index] = state
            self._render_steps()

    def on_packages(self, pkgs: list, command: str, manager: str):
        self._packages = (pkgs, command, manager)
        self._render_packages()
        self._set_status("install.status.waiting" if pkgs else "install.status.running")

    def toggle(self):
        if self.worker and self.worker.isRunning():
            self._stopping = True
            self._set_status("status.stopping")
            core.stop()
            QTimer.singleShot(3000, lambda: core.stop(force=True))
            return

        cfg = load_config(self.settings)

        def job(w: Worker):
            core.install(cfg, w.line.emit, w.step.emit, w.packages.emit)
            return 0

        self.log.clear()
        self.bus.begin()
        self._stopping = False
        self._states = ["pending"] * len(self._titles)
        self._render_steps()
        self.worker = Worker(job)
        self.worker.line.connect(self.bus.push)
        self.worker.step.connect(self.on_step)
        self.worker.packages.connect(self.on_packages)
        self.worker.finished_with.connect(self._on_finished)
        self._running = True
        self.action.setText(t("btn.stop"))
        self.action.setProperty("running", True)
        self.action.style().unpolish(self.action)
        self.action.style().polish(self.action)
        self._set_status("install.status.running")
        self.running_changed.emit(True)
        self.worker.start()

    def _on_finished(self, code: int):
        self._running = False
        self._packages = ([], "", "")
        self._render_packages()
        self.action.setText(t("btn.install"))
        self.action.setProperty("running", False)
        self.action.style().unpolish(self.action)
        self.action.style().polish(self.action)
        self.refresh()
        if self._status_key != "install.status.done":
            self._set_status("install.status.idle" if self._stopping else "install.status.failed")
        self.running_changed.emit(False)


class SettingsPage(QWidget):
    language_changed = Signal(str)
    proton_changed = Signal()

    def __init__(self, settings: QSettings):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 14, 14)
        root.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        root.addWidget(self.title)
        root.addSpacing(8)

        self.lang_switch = LangSwitch(i18n.language() == "ru")
        self.lang_switch.toggled.connect(
            lambda v: self.language_changed.emit("ru" if v else "en"))
        self.lang_row = SettingRow(self.lang_switch)
        root.addWidget(self.lang_row)

        self.proton = ProtonPicker(settings)
        self.proton.changed.connect(self.proton_changed)
        self.proton_row = SettingRow(self.proton)
        root.addWidget(self.proton_row)

        self.args = ArgsEditor(settings)
        self.args_row = SettingRow(self.args)
        root.addWidget(self.args_row)
        root.addStretch(1)

        self.retranslate()

    def set_locked(self, locked: bool):
        self.proton.setEnabled(not locked)

    def retranslate(self):
        self.title.setText(t("nav.settings"))
        self.lang_row.set_texts(t("settings.language.title"), t("settings.language.desc"))
        self.proton_row.set_texts(t("settings.proton.title"), t("settings.proton.desc"))
        self.proton.retranslate()
        self.args_row.set_texts(t("settings.args.title"), t("settings.args.desc"))
        self.args.retranslate()


class AddPage(QWidget):
    def __init__(self, settings: QSettings):
        super().__init__()
        self._shortcut_msg: tuple[str, dict] | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 14, 14)
        root.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        root.addWidget(self.title)
        root.addSpacing(8)

        self.debug_switch = ToggleSwitch(settings.value("debug", False, type=bool))
        self.debug_switch.toggled.connect(lambda v: settings.setValue("debug", v))
        self.debug_row = SettingRow(self.debug_switch)
        root.addWidget(self.debug_row)

        self.shortcut_status = QLabel("")
        self.shortcut_status.setObjectName("muted")
        self.shortcut_status.setWordWrap(True)
        self.shortcut_btn = QPushButton()
        self.shortcut_btn.clicked.connect(self.make_shortcut)
        self.shortcut_row = SettingRow(self.shortcut_btn)
        root.addWidget(self.shortcut_row)
        root.addWidget(self.shortcut_status)
        root.addStretch(1)

        self.retranslate()

    def retranslate(self):
        self.title.setText(t("nav.additional"))
        self.debug_row.set_texts(t("add.debug.title"), t("add.debug.desc"))
        self.shortcut_row.set_texts(t("add.shortcut.title"), t("add.shortcut.desc"))
        self.shortcut_btn.setText(t("add.shortcut.btn"))
        if self._shortcut_msg:
            key, kw = self._shortcut_msg
            self.shortcut_status.setText(t(key, **kw))

    def _set_shortcut_msg(self, key: str, **kw):
        self._shortcut_msg = (key, kw)
        self.shortcut_status.setText(t(key, **kw))

    def make_shortcut(self):
        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            command = [sys.executable, str(Path(__file__).resolve())]
        try:
            path = core.create_shortcut(ICON_PNG, command)
        except (core.SetupError, OSError) as e:
            self._set_shortcut_msg("add.shortcut.error", err=e)
            return
        self._set_shortcut_msg("add.shortcut.ok", path=path)


class AboutPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 14, 14)
        root.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        root.addWidget(self.title)
        root.addWidget(QLabel(f"Majestic Linux  v{APP_VERSION}"))
        self.info = QLabel()
        self.info.setObjectName("muted")
        root.addWidget(self.info)
        self.gh = QPushButton()
        self.gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        root.addWidget(self.gh, alignment=Qt.AlignLeft)
        root.addStretch(1)
        self.retranslate()

    def retranslate(self):
        self.title.setText(t("nav.about"))
        self.info.setText(t("about.info"))
        self.gh.setText(t("about.github"))


NAV_KEYS = ("nav.general", "nav.install", "nav.settings", "nav.additional", "nav.about")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Majestic Linux")
        self.resize(WIN_W, WIN_H)
        core.STATE.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(core.STATE / "config.ini"), QSettings.IniFormat)
        i18n.set_language(str(self.settings.value("language", i18n.DEFAULT)))
        logs.SessionLog(core.LOGS_DIR).cleanup((core.LEGACY_LOG,))

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        side = QWidget()
        side.setFixedWidth(190)
        side.setStyleSheet("background: #1b1b1b;")
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 12, 0, 8)
        side_lay.setSpacing(8)

        brand = QHBoxLayout()
        brand.setContentsMargins(12, 0, 12, 0)
        logo = QLabel()
        logo.setPixmap(QIcon(str(ICON_PATH)).pixmap(32, 32))
        name = QLabel("Majestic Linux")
        name.setStyleSheet("font-weight: bold;")
        brand.addWidget(logo)
        brand.addWidget(name, 1)
        side_lay.addLayout(brand)

        self.nav = QListWidget()
        for key in NAV_KEYS:
            self.nav.addItem(t(key))
        side_lay.addWidget(self.nav, 1)
        outer.addWidget(side)

        self.stack = QStackedWidget()
        self.general = GeneralPage(self.settings)
        self.installer = InstallPage(self.settings)
        self.settings_page = SettingsPage(self.settings)
        self.pages = [self.general, self.installer, self.settings_page,
                      AddPage(self.settings), AboutPage()]
        for page in self.pages:
            self.stack.addWidget(page)
        self.settings_page.language_changed.connect(self.apply_language)
        self.settings_page.proton_changed.connect(self.on_proton_changed)
        self.general.running_changed.connect(self.installer.set_locked)
        self.general.running_changed.connect(self.settings_page.set_locked)
        self.installer.running_changed.connect(self.general.set_locked)
        self.installer.running_changed.connect(self.settings_page.set_locked)
        outer.addWidget(self.stack, 1)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

    def closeEvent(self, event):
        workers = [w for w in (self.general.worker, self.installer.worker) if w and w.isRunning()]
        if workers:
            core.stop(force=True)
            for w in workers:
                w.wait(3000)
        self.general.bus.close()
        self.installer.bus.close()
        super().closeEvent(event)

    def on_proton_changed(self):
        self.general.refresh()
        self.nav.setCurrentRow(1)

    def apply_language(self, code: str):
        i18n.set_language(code)
        self.settings.setValue("language", i18n.language())
        for i, key in enumerate(NAV_KEYS):
            self.nav.item(i).setText(t(key))
        for page in self.pages:
            page.retranslate()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(DESKTOP_ID)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(STYLE)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())