"""新 CAN 多指令窗口（v1，独立于旧 CanWindow）。

布局对齐 docs/ui_mockup/ui_mockup_v3.html：
- 顶部：A/B 总线独立开关卡片（各通道可单独打开/关闭设备）
- 中部：A/B Tab 指令配置，每条指令 = 气泡横条卡片
  - 双击展开帧明细；右键菜单（单发一次/启停定时/复制/编辑帧/删除）
  - 发送条数（-1=无限）默认；运行期间配置区锁定只读
- 底部：统一监视流（气泡行 + A/B、TX/RX/ERR 过滤 + 统计条）
- 配置导入/导出：JSON / Excel
"""
import os
import json
import time
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QCursor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QListWidget, QListWidgetItem, QFrame,
    QCheckBox, QPlainTextEdit, QLineEdit, QMessageBox, QMenu, QAction,
    QFileDialog, QAbstractItemView, QSizePolicy, QStyleOption, QStyle
)

from JiangCan_Tools.ECAN import ECAN, BaudRate, CAN_OBJ, Channel1, Channel2
from WorkClass.CANCommandScheduler import (
    CanCommand, CanFrame, parse_hex_bytes, MIN_INTERVAL_MS, INFINITE,
    CANCommandScheduler, PRESETS_A, PRESETS_B,
)
from WorkClass.CanStreamWorkers import CanTxWorker, CanRecvWorker
from logging_config import log_print

CHAN_A = 'A'
CHAN_B = 'B'
STATUS_OK = 1

LIGHT_QSS = """
QDialog, QWidget#root { background:#eef2f9; }
QWidget#busCard { background:#fff; border:1px solid #e2e8f2; border-radius:10px; }
QWidget#panelCard { background:#fff; border:1px solid #e2e8f2; border-radius:12px; }
QLabel#appTitle { font-size:16px; font-weight:700; color:#1d2633; }
QLabel#busName { font-weight:700; color:#1d2633; }
QLabel#secTitle { font-size:13.5px; font-weight:700; color:#1d2633; }
QLabel#muted { color:#7c8798; }
QLabel#mono { font-family:'Cascadia Code','Consolas',monospace; color:#1d2633; }
QPushButton { background:#fff; border:1px solid #d4dbe8; border-radius:8px; padding:5px 12px; color:#1d2633; }
QPushButton:hover { border-color:#2f6fed; color:#2f6fed; }
QPushButton:disabled { color:#b0b8c6; border-color:#e2e8f2; background:#f4f6fb; }
QPushButton#primary { background:#2f6fed; color:#fff; border:none; }
QPushButton#primary:hover { background:#1f5ee8; }
QPushButton#danger { color:#e5484d; }
QPushButton#small { padding:2px 8px; font-size:11px; border-radius:6px; }
QListWidget#cmdList { background:transparent; border:none; outline:none; }
QTabWidget::pane { border:1px solid #e2e8f2; border-radius:10px; top:-1px; background:#fff; }
QTabBar::tab { background:transparent; color:#7c8798; padding:7px 18px; border:1px solid transparent; border-bottom:none; font-weight:600; }
QTabBar::tab:selected { background:#fff; color:#1d2633; border:1px solid #e2e8f2; border-bottom:none; border-radius:8px 8px 0 0; }
QComboBox, QLineEdit { background:#fff; border:1px solid #d4dbe8; border-radius:6px; padding:3px 8px; }
QComboBox:disabled, QLineEdit:disabled { color:#b0b8c6; background:#f4f6fb; }
QTextEdit { background:#fff; border:1px solid #e2e8f2; border-radius:8px; }
QScrollBar:vertical { background:transparent; width:8px; }
QScrollBar::handle:vertical { background:#c6cfdd; border-radius:4px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QMenu { background:#fff; border:1px solid #e2e8f2; border-radius:8px; padding:4px; }
QMenu::item { padding:6px 22px; border-radius:6px; }
QMenu::item:selected { background:#e9f0ff; color:#2f6fed; }
"""

DARK_QSS = """
QDialog, QWidget#root { background:#0d1117; }
QWidget#busCard { background:#161c26; border:1px solid #263141; border-radius:10px; }
QWidget#panelCard { background:#161c26; border:1px solid #263141; border-radius:12px; }
QLabel#appTitle { font-size:16px; font-weight:700; color:#e8edf5; }
QLabel#busName { font-weight:700; color:#e8edf5; }
QLabel#secTitle { font-size:13.5px; font-weight:700; color:#e8edf5; }
QLabel#muted { color:#8d99a8; }
QLabel#mono { font-family:'Cascadia Code','Consolas',monospace; color:#e8edf5; }
QPushButton { background:#1c2129; border:1px solid #3a4350; border-radius:8px; padding:5px 12px; color:#e8edf5; }
QPushButton:hover { border-color:#4c8dff; color:#4c8dff; }
QPushButton:disabled { color:#4b5563; border-color:#263141; background:#171b22; }
QPushButton#primary { background:#4c8dff; color:#fff; border:none; }
QPushButton#primary:hover { background:#6ba2ff; }
QPushButton#danger { color:#f2555a; }
QPushButton#small { padding:2px 8px; font-size:11px; border-radius:6px; }
QListWidget#cmdList { background:transparent; border:none; outline:none; }
QTabWidget::pane { border:1px solid #263141; border-radius:10px; top:-1px; background:#161c26; }
QTabBar::tab { background:transparent; color:#8d99a8; padding:7px 18px; border:1px solid transparent; border-bottom:none; font-weight:600; }
QTabBar::tab:selected { background:#161c26; color:#e8edf5; border:1px solid #263141; border-bottom:none; border-radius:8px 8px 0 0; }
QComboBox, QLineEdit { background:#1c2129; border:1px solid #3a4350; border-radius:6px; padding:3px 8px; color:#e8edf5; }
QComboBox:disabled, QLineEdit:disabled { color:#4b5563; background:#171b22; }
QTextEdit { background:#161c26; border:1px solid #263141; border-radius:8px; color:#e8edf5; }
QScrollBar:vertical { background:transparent; width:8px; }
QScrollBar::handle:vertical { background:#3a4350; border-radius:4px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QMenu { background:#1b2330; border:1px solid #263141; border-radius:8px; padding:4px; }
QMenu::item { padding:6px 22px; border-radius:6px; color:#e8edf5; }
QMenu::item:selected { background:#1b2a47; color:#4c8dff; }
"""

# 胶囊配色（浅/深）
CHIP_FRAME = "background:{bg}; color:{fg}; border:1px solid transparent; border-radius:10px; padding:2px 10px; font-size:11px;"
CHIP_BLUE = CHIP_FRAME.format(bg="#e9f0ff", fg="#2f6fed")
CHIP_BLUE_D = CHIP_FRAME.format(bg="#1b2a47", fg="#4c8dff")
CHIP_GREEN = CHIP_FRAME.format(bg="#e5f6ef", fg="#0e9f6e")
CHIP_GREEN_D = CHIP_FRAME.format(bg="#0f2e22", fg="#2fc48a")
CHIP_GRAY = CHIP_FRAME.format(bg="#eef1f6", fg="#7c8798")
CHIP_GRAY_D = CHIP_FRAME.format(bg="#222b38", fg="#8d99a8")
CHIP_ORANGE = CHIP_FRAME.format(bg="#fdf2dd", fg="#f29400")
CHIP_ORANGE_D = CHIP_FRAME.format(bg="#32260d", fg="#f6b64a")
CHIP_PURPLE = CHIP_FRAME.format(bg="#f0eafd", fg="#8b5cf6")
CHIP_PURPLE_D = CHIP_FRAME.format(bg="#2b2044", fg="#a78bfa")
BADGE_RED = CHIP_FRAME.format(bg="#fdeaea", fg="#e5484d")
BADGE_RED_D = CHIP_FRAME.format(bg="#3a1a1d", fg="#f2555a")


def _chip_css(color, dark):
    if color == 'blue':
        return CHIP_BLUE_D if dark else CHIP_BLUE
    if color == 'green':
        return CHIP_GREEN_D if dark else CHIP_GREEN
    if color == 'orange':
        return CHIP_ORANGE_D if dark else CHIP_ORANGE
    if color == 'purple':
        return CHIP_PURPLE_D if dark else CHIP_PURPLE
    if color == 'red':
        return BADGE_RED_D if dark else BADGE_RED
    return CHIP_GRAY_D if dark else CHIP_GRAY


def _now_ms():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class _Chip(QLabel):
    def __init__(self, text, color='gray', dark=False, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(_chip_css(color, dark))
        self.setContentsMargins(8, 2, 8, 2)


class _CommandCard(QWidget):
    """单条指令气泡卡：双击展开/收起，右键出菜单，开关启停。"""
    dblClicked = pyqtSignal(object)
    toggled = pyqtSignal(object, bool)
    contextMenu = pyqtSignal(object)

    def __init__(self, cmd, dark=False, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.dark = dark
        self._open = False
        self.setObjectName('cmdCard')
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.row = QFrame()
        rh = QHBoxLayout(self.row)
        rh.setContentsMargins(12, 8, 12, 8)
        rh.setSpacing(8)

        # 通道徽标
        self.badge_ch = QLabel('A' if self.cmd.channel == CHAN_A else 'B')
        self.badge_ch.setAlignment(Qt.AlignCenter)
        self.badge_ch.setFixedSize(30, 30)
        color_ch = '#2f6fed' if self.cmd.channel == CHAN_A else '#8b5cf6'
        self.badge_ch.setStyleSheet(
            "background:%s; color:#fff; border-radius:9px; font-weight:800;" % color_ch)
        rh.addWidget(self.badge_ch)

        # 名称 + 首帧ID
        nm_box = QVBoxLayout()
        nm_box.setSpacing(0)
        self.lb_name = QLabel(self.cmd.name)
        self.lb_name.setStyleSheet("font-weight:700; color:%s;" % ("#1d2633" if not self.dark else "#e8edf5"))
        self.lb_sub = QLabel('')
        self.lb_sub.setStyleSheet("font-size:10px; color:#7c8798;")
        nm_box.addWidget(self.lb_name)
        nm_box.addWidget(self.lb_sub)
        nm_w = QWidget()
        nm_w.setLayout(nm_box)
        rh.addWidget(nm_w, 1)

        self.chip_frames = _Chip('%d 帧' % len(self.cmd.frames), 'blue', self.dark)
        rh.addWidget(self.chip_frames)
        self.chip_interval = _Chip('⏱ %d ms' % self.cmd.interval_ms, 'orange', self.dark)
        rh.addWidget(self.chip_interval)
        self.chip_count = _Chip(self._count_text(), 'green', self.dark)
        rh.addWidget(self.chip_count)

        self.lb_result = QLabel('—')
        self.lb_result.setStyleSheet("font-size:10px; color:#7c8798; padding:0 6px;")
        rh.addWidget(self.lb_result)

        self.badge_state = QLabel('停止')
        self.badge_state.setStyleSheet("font-size:10px; padding:2px 10px; border-radius:9px; color:#7c8798; background:#eef1f6;")
        rh.addWidget(self.badge_state)

        # 开关
        self.sw = QCheckBox()
        self.sw.setChecked(self.cmd.enabled)
        self.sw.stateChanged.connect(lambda _: self._on_toggle())
        rh.addWidget(self.sw)

        lay.addWidget(self.row)

        # 展开帧明细区
        self.detail = QWidget()
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(16, 2, 16, 8)
        dl.setSpacing(2)
        self.frames_box = QVBoxLayout()
        self.frames_box.setSpacing(2)
        dl.addLayout(self.frames_box)
        self.detail.setVisible(False)
        lay.addWidget(self.detail)

        self._refresh_row_style()
        self.refresh_frames()

    def _count_text(self):
        return '⇉ ∞ 无限' if self.cmd.is_infinite else '⇉ ×%d 次' % self.cmd.count

    def _refresh_row_style(self):
        if self._open:
            bg = '#e9f0ff' if not self.dark else '#1b2a47'
            bd = '#2f6fed' if not self.dark else '#4c8dff'
        elif self.cmd.enabled:
            bg = '#f3f7ff' if not self.dark else '#1b2330'
            bd = '#c9d9fb' if not self.dark else '#263141'
        else:
            bg = '#ffffff' if not self.dark else '#161c26'
            bd = '#e2e8f2' if not self.dark else '#263141'
        self.row.setStyleSheet(
            "QFrame { background:%s; border:1px solid %s; border-radius:12px; }" % (bg, bd))

    def refresh_frames(self):
        while self.frames_box.count():
            it = self.frames_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        for i, f in enumerate(self.cmd.frames):
            fr = QFrame()
            fr.setStyleSheet("background:%s; border-radius:8px;" %
                             ("#f8fafd" if not self.dark else "#1b2330"))
            fl = QHBoxLayout(fr)
            fl.setContentsMargins(10, 2, 10, 2)
            seq = QLabel('#%d' % (i + 1))
            seq.setStyleSheet("color:#7c8798; min-width:24px; font-family:'Consolas';")
            cid = QLabel('0x%X' % f.id)
            cid.setStyleSheet("font-weight:700; color:%s; font-family:'Consolas';" %
                              ("#2f6fed" if not self.dark else "#4c8dff"))
            dhex = QLabel(' '.join('%02X' % b for b in f.data))
            dhex.setStyleSheet("color:#7c8798; font-family:'Consolas';")
            fl.addWidget(seq)
            fl.addWidget(cid)
            fl.addWidget(dhex)
            fl.addStretch(1)
            self.frames_box.addWidget(fr)

    def update_from_cmd(self):
        self.lb_name.setText(self.cmd.name)
        self.lb_sub.setText('首帧ID: 0x%X' % self.cmd.frames[0].id if self.cmd.frames else '')
        self.chip_frames.setText('%d 帧' % len(self.cmd.frames))
        self.chip_interval.setText('⏱ %d ms' % self.cmd.interval_ms)
        self.chip_count.setText(self._count_text())
        self.sw.blockSignals(True)
        self.sw.setChecked(self.cmd.enabled)
        self.sw.blockSignals(False)
        if self.cmd.enabled:
            self.badge_state.setText('运行中')
            self.badge_state.setStyleSheet("font-size:10px; padding:2px 10px; border-radius:9px; color:%s; background:%s;" %
                                           ("#2f6fed" if not self.dark else "#4c8dff",
                                            "#e9f0ff" if not self.dark else "#1b2a47"))
        else:
            self.badge_state.setText('停止')
            self.badge_state.setStyleSheet("font-size:10px; padding:2px 10px; border-radius:9px; color:#7c8798; background:#eef1f6;")
        self._refresh_row_style()

    def set_result(self, ok):
        if ok is None:
            self.lb_result.setText('—')
            self.lb_result.setStyleSheet("font-size:10px; color:#7c8798; padding:0 6px;")
        elif ok:
            self.lb_result.setText('最近成功 ' + _now_ms())
            self.lb_result.setStyleSheet("font-size:10px; color:#0e9f6e; padding:0 6px; font-weight:600;")
        else:
            self.lb_result.setText('TX 失败')
            self.lb_result.setStyleSheet("font-size:10px; color:#e5484d; padding:0 6px; font-weight:600;")

    # ---------- 事件 ----------
    def _on_toggle(self):
        self.cmd.enabled = self.sw.isChecked()
        self.toggled.emit(self, self.cmd.enabled)

    def set_open(self, open_):
        self._open = open_
        self.detail.setVisible(open_)
        self._refresh_row_style()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dblClicked.emit(self)

    def contextMenuEvent(self, e):
        self.contextMenu.emit(self)

    def paintEvent(self, e):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)
        p.end()
        super().paintEvent(e)

class NewCanWindow(QDialog):
    """主窗口：总线卡片 + A/B Tab 指令配置 + 统一监视流。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CAN 新版 · 多指令定时发送")
        self.resize(1280, 800)
        self._dark = False
        self._running = False

        # 总线
        self._dev = None
        self._canA = None
        self._canB = None
        self._txA = None
        self._txB = None
        self._rxA = None
        self._rxB = None

        # 数据
        self._cmdsA = []
        self._cmdsB = []

        # 统计
        self._tx_cnt = {'A': 0, 'B': 0}
        self._rx_cnt = {'A': 0, 'B': 0}
        self._err_cnt = {'A': 0, 'B': 0}

        # 调度
        self.sched = CANCommandScheduler()
        self.sched.set_callback(self._on_cmd_due)

        self._build_ui()
        self._load_defaults()
        self._apply_theme()

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._on_ui_tick)
        self._ui_timer.start(10)   # 10ms 心跳，支撑最小 10ms 发送间隔

    # =========================================================
    # UI 构建
    # =========================================================
    def _build_ui(self):
        self.setObjectName('root')
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # 顶栏
        top = QHBoxLayout()
        self.lb_title = QLabel("CAN 新版 · 多指令定时发送")
        self.lb_title.setObjectName('appTitle')
        top.addWidget(self.lb_title)
        top.addStretch(1)

        btn_import = QPushButton("导入配置")
        btn_import.setObjectName('small')
        btn_import.clicked.connect(self._import_cfg_menu)
        top.addWidget(btn_import)
        btn_export = QPushButton("导出配置")
        btn_export.setObjectName('small')
        btn_export.clicked.connect(self._export_cfg_menu)
        top.addWidget(btn_export)

        btn_theme = QPushButton("深色")
        btn_theme.setObjectName('small')
        btn_theme.clicked.connect(self._toggle_dark)
        top.addWidget(btn_theme)

        self.btn_run = QPushButton("▶ 开始发送（锁定配置）")
        self.btn_run.setObjectName('primary')
        self.btn_run.clicked.connect(self._toggle_running)
        top.addWidget(self.btn_run)
        root.addLayout(top)

        # 总线卡片
        bus_row = QHBoxLayout()
        bus_row.setSpacing(10)
        self._busA = self._make_bus_card(CHAN_A)
        self._busB = self._make_bus_card(CHAN_B)
        bus_row.addWidget(self._busA)
        bus_row.addWidget(self._busB)
        root.addLayout(bus_row)

        # 指令配置 Tab
        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_cmd_tab(CHAN_A), "通道 A")
        self.tabs.addTab(self._make_cmd_tab(CHAN_B), "通道 B")
        root.addWidget(self.tabs, 2)

        # 监视区
        root.addWidget(self._make_monitor_panel(), 3)

        # 底部统计
        self.lb_stats = QLabel("TX A 0 | TX B 0 | RX A 0 | RX B 0 | 错误 A 0 | 错误 B 0")
        self.lb_stats.setObjectName('muted')
        root.addWidget(self.lb_stats)

    def _make_bus_card(self, ch):
        w = QWidget()
        w.setObjectName('busCard')
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 10, 14, 10)

        blk = QLabel(ch)
        blk.setFixedSize(38, 38)
        blk.setAlignment(Qt.AlignCenter)
        blk.setStyleSheet("font-weight:800; color:#fff; font-size:15px; border-radius:10px; background:%s;" %
                          ("#2f6fed" if ch == CHAN_A else "#8b5cf6"))
        lay.addWidget(blk)

        col = QVBoxLayout()
        col.setSpacing(2)
        h = QHBoxLayout()
        name = QLabel("通道 %s" % ch)
        name.setObjectName('busName')
        self.st_lbl = QLabel("○ 已关闭")
        self.st_lbl.setObjectName('busSt')
        h.addWidget(name)
        h.addWidget(self.st_lbl)
        col.addLayout(h)
        stat = QLabel("波特率 500K  TX 0  RX 0  ERR 0")
        stat.setObjectName('muted')
        col.addWidget(stat)
        lay.addLayout(col, 1)

        btn = QPushButton("打开设备")
        btn.setObjectName('small')
        btn.clicked.connect(lambda _=False, c=ch: self._toggle_bus(c))
        lay.addWidget(btn)

        if ch == CHAN_A:
            self.busA_btn, self.busA_st, self.busA_stat = btn, self.st_lbl, stat
        else:
            self.busB_btn, self.busB_st, self.busB_stat = btn, self.st_lbl, stat
        return w

    def _make_cmd_tab(self, ch):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("＋ 添加指令")
        btn_add.setObjectName('small')
        btn_add.clicked.connect(lambda: self._add_command(ch))
        toolbar.addWidget(btn_add)
        btn_dup = QPushButton("复制选中")
        btn_dup.setObjectName('small')
        btn_dup.clicked.connect(lambda: self._copy_command(ch))
        toolbar.addWidget(btn_dup)
        btn_del = QPushButton("删除选中")
        btn_del.setObjectName('small')
        btn_del.setStyleSheet("color:#e5484d;")
        btn_del.clicked.connect(lambda: self._remove_command(ch))
        toolbar.addWidget(btn_del)
        toolbar.addStretch(1)
        btn_preset = QPushButton("从预设添加 ▼")
        btn_preset.setObjectName('small')
        btn_preset.clicked.connect(lambda: self._preset_menu(ch))
        toolbar.addWidget(btn_preset)
        lay.addLayout(toolbar)

        lst = QListWidget()
        lst.setObjectName('cmdList')
        lst.setSelectionMode(QAbstractItemView.SingleSelection)
        lst.setSpacing(6)
        # 双击展开由卡片自身 mouseDoubleClickEvent 处理，避免与 itemDoubleClicked 双触发
        lst.setContextMenuPolicy(Qt.CustomContextMenu)
        lst.customContextMenuRequested.connect(self._on_ctx)
        lst.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        lay.addWidget(lst, 1)

        btns = {'add': btn_add, 'dup': btn_dup, 'del': btn_del, 'preset': btn_preset}
        if ch == CHAN_A:
            self.listA = lst
            self.toolBtnsA = btns
        else:
            self.listB = lst
            self.toolBtnsB = btns
        return tab

    def _make_monitor_panel(self):
        panel = QWidget()
        panel.setObjectName('panelCard')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        t = QLabel("收发监视流")
        t.setObjectName('secTitle')
        head.addWidget(t)
        tip = QLabel(" 每行一帧 · 最新在底部")
        tip.setObjectName('muted')
        head.addWidget(tip)
        head.addStretch(1)

        self.mon = QPlainTextEdit()
        self.mon.setReadOnly(True)
        self.mon.setMaximumBlockCount(3000)
        self.mon.setStyleSheet(
            "font-family:'Cascadia Code','Consolas',monospace; font-size:11px;" +
            ("color:#1d2633; background:#fff; border:1px solid #e2e8f2; border-radius:8px;"
             if not self._dark else
             "color:#e8edf5; background:#161c26; border:1px solid #263141; border-radius:8px;"))
        lay.addWidget(self.mon, 1)
        return panel

    # =========================================================
    # 总线开关
    # =========================================================
    def _toggle_bus(self, ch):
        if self._bus_open(ch):
            self._close_bus(ch)
        else:
            self._open_bus(ch)

    def _bus_open(self, ch):
        return (self._canA is not None) if ch == CHAN_A else (self._canB is not None)

    def _open_bus(self, ch):
        try:
            if self._dev is None:
                dll = os.path.join(os.getcwd(), "JiangCan_Tools", "ECanVci64.dll")
                if not os.path.exists(dll):
                    dll = os.path.join(os.getcwd(), ".\\dist\\Can_Frame_Deal\\ECanVci64.dll")
                ECAN.open(0, 0, dll)
                self._dev = True
            if ECAN.is_open is False:
                self._bus_error(ch, "设备未打开")
                return

            dev = ECAN(Channel1 if ch == CHAN_A else Channel2)
            if not dev.config(BaudRate.BAUD_500K):
                self._bus_error(ch, "config 失败")
                return
            if not dev.start():
                self._bus_error(ch, "start 失败")
                return

            if ch == CHAN_A:
                self._canA = dev
                self._txA = CanTxWorker(dev, CHAN_A, self)
                self._rxA = CanRecvWorker(dev, CHAN_A, self)
                self._txA.tx_result.connect(self._on_tx_result)
                self._rxA.rx_frame.connect(self._on_rx_frame)
                self._txA.start()
                self._rxA.start()
            else:
                self._canB = dev
                self._txB = CanTxWorker(dev, CHAN_B, self)
                self._rxB = CanRecvWorker(dev, CHAN_B, self)
                self._txB.tx_result.connect(self._on_tx_result)
                self._rxB.rx_frame.connect(self._on_rx_frame)
                self._txB.start()
                self._rxB.start()
            self._bus_set_state(ch, True)
            self._mon_append("SYSTEM", "通道 %s 已打开" % ch, 'info')
        except Exception as e:
            log_print("open bus %s error: %s" % (ch, e))
            self._bus_error(ch, str(e))

    def _close_bus(self, ch):
        try:
            if ch == CHAN_A:
                if self._txA:
                    self._txA.shutdown(); self._txA.quit(); self._txA.wait(1200)
                if self._rxA:
                    self._rxA.shutdown(); self._rxA.quit(); self._rxA.wait(1200)
                self._txA = self._rxA = self._canA = None
            else:
                if self._txB:
                    self._txB.shutdown(); self._txB.quit(); self._txB.wait(1200)
                if self._rxB:
                    self._rxB.shutdown(); self._rxB.quit(); self._rxB.wait(1200)
                self._txB = self._rxB = self._canB = None
            self._bus_set_state(ch, False)
            self._mon_append("SYSTEM", "通道 %s 已关闭" % ch, 'info')
            if self._canA is None and self._canB is None and self._dev is not None:
                if ECAN.is_open:
                    ECAN.close()
                self._dev = None
        except Exception as e:
            log_print("close bus %s error: %s" % (ch, e))
            self._bus_error(ch, str(e))

    def _bus_set_state(self, ch, open_):
        btn, st = (self.busA_btn, self.busA_st) if ch == CHAN_A else (self.busB_btn, self.busB_st)
        btn.setText("关闭设备" if open_ else "打开设备")
        st.setText("● 已开启" if open_ else "○ 已关闭")
        st.setStyleSheet("color:#0e9f6e; font-weight:600;" if open_ else "color:#7c8798; font-weight:600;")

    def _bus_error(self, ch, msg):
        self._mon_append("SYSTEM", "通道 %s 错误: %s" % (ch, msg), 'err')
        QMessageBox.warning(self, "通道 %s" % ch, msg)

    # =========================================================
    # 指令数据管理
    # =========================================================
    def _cmds(self, ch):
        return self._cmdsA if ch == CHAN_A else self._cmdsB

    def _load_defaults(self):
        for c in PRESETS_A[:3]:
            self._cmdsA.append(c.copy())
        for c in PRESETS_B[:2]:
            self._cmdsB.append(c.copy())
        self._rebuild_lists()
        self.sched.set_commands(self._cmdsA + self._cmdsB)

    def _rebuild_lists(self):
        for ch, lst, cmds in ((CHAN_A, self.listA, self._cmdsA),
                              (CHAN_B, self.listB, self._cmdsB)):
            lst.clear()
            for c in cmds:
                card = _CommandCard(c, dark=self._dark)
                card.dblClicked.connect(self._on_dbl_card)
                card.toggled.connect(self._on_toggle_cmd)
                card.contextMenu.connect(self._on_card_menu)
                it = QListWidgetItem()
                it.setSizeHint(card.sizeHint())
                it.setData(Qt.UserRole, c)
                lst.addItem(it)
                lst.setItemWidget(it, card)
        self.sched.set_commands(self._cmdsA + self._cmdsB)

    def _card_of(self, cmd):
        for lst in (self.listA, self.listB):
            for i in range(lst.count()):
                it = lst.item(i)
                if it.data(Qt.UserRole) is cmd:
                    return lst.itemWidget(it)
        return None

    def _card_lists(self, card):
        for lst in (self.listA, self.listB):
            if lst.itemWidget(lst.currentItem()) is card:
                return lst
        return None

    def _add_command(self, ch):
        if self._running:
            return
        c = CanCommand("新指令 %d" % (len(self._cmds(ch)) + 1), ch, 500, INFINITE, False,
                       [CanFrame(0x1E180000, [0x00])])
        self._cmds(ch).append(c)
        self.sched.add(c)
        self._rebuild_lists()

    def _copy_command(self, ch):
        lst = self.listA if ch == CHAN_A else self.listB
        it = lst.currentItem()
        if not it:
            QMessageBox.information(self, "复制", "请先选择一条指令")
            return
        c = it.data(Qt.UserRole)
        n = c.copy()
        n.name = c.name + " (复制)"
        n.enabled = False
        self._cmds(ch).append(n)
        self.sched.add(n)
        self._rebuild_lists()

    def _remove_command(self, ch):
        lst = self.listA if ch == CHAN_A else self.listB
        it = lst.currentItem()
        if not it:
            QMessageBox.information(self, "删除", "请先选择一条指令")
            return
        c = it.data(Qt.UserRole)
        if c.enabled and self._running:
            QMessageBox.warning(self, "删除", "运行中不能删除启用指令")
            return
        self._cmds(ch).remove(c)
        self.sched.remove(c)
        self._rebuild_lists()

    def _preset_menu(self, ch):
        menu = QMenu(self)
        for p in (PRESETS_A if ch == CHAN_A else PRESETS_B):
            act = QAction("%s (%d帧)" % (p.name, len(p.frames)), menu)
            act.triggered.connect(lambda _=False, pp=p: self._add_preset(ch, pp))
            menu.addAction(act)
        menu.exec_(QCursor.pos())

    def _add_preset(self, ch, preset):
        if self._running:
            return
        c = preset.copy()
        c.channel = ch
        c.enabled = False
        self._cmds(ch).append(c)
        self.sched.add(c)
        self._rebuild_lists()

    # =========================================================
    # 右键菜单 / 编辑
    # =========================================================
    def _on_card_menu(self, card):
        menu = QMenu(self)
        a1 = QAction("▶ 立即发送一次", menu)
        a1.triggered.connect(lambda: self._send_once(card.cmd))
        menu.addAction(a1)
        if card.cmd.enabled:
            a2 = QAction("⏹ 停止定时", menu)
            a2.triggered.connect(lambda: self._stop_cmd(card.cmd))
            menu.addAction(a2)
        elif not self._running:
            a2 = QAction("⏱ 启用定时", menu)
            a2.triggered.connect(lambda: self._enable_cmd(card.cmd))
            menu.addAction(a2)
        if not self._running:
            menu.addSeparator()
            a3 = QAction("✎ 编辑（改帧/ID/间隔/次数）", menu)
            a3.triggered.connect(lambda: self._edit_cmd(card.cmd))
            menu.addAction(a3)
            a4 = QAction("复制", menu)
            a4.triggered.connect(lambda: self._copy_cmd_menu(card.cmd))
            menu.addAction(a4)
            menu.addSeparator()
            a5 = QAction("删除", menu)
            a5.triggered.connect(lambda: self._delete_cmd_menu(card.cmd))
            menu.addAction(a5)
        menu.exec_(QCursor.pos())

    def _copy_cmd_menu(self, cmd):
        if self._running:
            return
        n = cmd.copy()
        n.name = cmd.name + " (复制)"
        n.enabled = False
        self._cmds(cmd.channel).append(n)
        self.sched.add(n)
        self._rebuild_lists()

    def _delete_cmd_menu(self, cmd):
        if cmd.enabled and self._running:
            QMessageBox.warning(self, "删除", "运行中不能删除启用指令")
            return
        self._cmds(cmd.channel).remove(cmd)
        self.sched.remove(cmd)
        self._rebuild_lists()

    def _edit_cmd(self, cmd):
        if self._running:
            QMessageBox.warning(self, "编辑", "运行中已锁定")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑指令: %s" % cmd.name)
        dlg.resize(560, 340)
        lay = QVBoxLayout(dlg)

        f1 = QHBoxLayout()
        f1.addWidget(QLabel("名称"))
        e_name = QLineEdit(cmd.name)
        f1.addWidget(e_name, 1)
        lay.addLayout(f1)

        f2 = QHBoxLayout()
        f2.addWidget(QLabel("间隔 ms"))
        e_int = QLineEdit(str(cmd.interval_ms))
        f2.addWidget(e_int)
        f2.addWidget(QLabel("次数(0=无限)"))
        e_cnt = QLineEdit("0" if cmd.is_infinite else str(cmd.count))
        f2.addWidget(e_cnt)
        lay.addLayout(f2)

        tip = QLabel("帧列表：每行一帧，格式  <ID(hex)>  <数据hex,≤8字节>\n例:  1E180015  00 23 00 01 20 1F 1E 1D\n同指令不同 ID：每帧可填不同 ID。")
        tip.setWordWrap(True)
        tip.setObjectName('muted')
        lay.addWidget(tip)

        e_frames = QTextEdit()
        e_frames.setPlainText("\n".join("%X %s" % (f.id, ' '.join('%02X' % b for b in f.data))
                                        for f in cmd.frames))
        lay.addWidget(e_frames, 1)

        btns = QHBoxLayout()
        ok = QPushButton("保存")
        ok.setObjectName('primary')
        ok.clicked.connect(lambda: self._do_edit(cmd, dlg, e_name, e_int, e_cnt, e_frames))
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)
        dlg.exec_()

    def _do_edit(self, cmd, dlg, e_name, e_int, e_cnt, e_frames):
        try:
            interval = int(e_int.text())
            if interval < MIN_INTERVAL_MS:
                QMessageBox.warning(dlg, "间隔", "最小 10ms")
                return
            cnt_txt = e_cnt.text().strip()
            cnt = 0 if not cnt_txt else int(cnt_txt)
            frames = []
            for ln in e_frames.toPlainText().splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                parts = ln.split()
                if len(parts) < 2:
                    raise ValueError("帧行缺少 ID 或数据: %s" % ln)
                fid = int(parts[0], 16)
                data = parse_hex_bytes(" ".join(parts[1:]))
                if data is None or len(data) > 8:
                    raise ValueError("数据需为 ≤8 字节 hex: %s" % ln)
                frames.append(CanFrame(fid, data))
            if not frames:
                raise ValueError("至少需要 1 帧")
            cmd.name = e_name.text().strip() or cmd.name
            cmd.interval_ms = interval
            cmd.count = cnt if cnt > 0 else INFINITE
            cmd.frames = frames
            card = self._card_of(cmd)
            if card:
                card.update_from_cmd()
                card.refresh_frames()
                self._sync_item_height(card)
            dlg.accept()
        except Exception as ex:
            QMessageBox.warning(dlg, "格式错误", str(ex))

    # =========================================================
    # 启停 / 发送
    # =========================================================
    def _sync_item_height(self, card):
        for lst in (self.listA, self.listB):
            for i in range(lst.count()):
                it = lst.item(i)
                if lst.itemWidget(it) is card:
                    card.adjustSize()
                    it.setSizeHint(card.sizeHint())
                    lst.update()
                    return

    def _on_dbl_card(self, card):
        card.set_open(not card._open)
        # 展开/收起后需更新 QListWidgetItem 高度，否则帧明细被裁切
        self._sync_item_height(card)

    def _on_ctx(self, pos):
        lst = self.sender()
        it = lst.itemAt(pos)
        if it:
            lst.setCurrentItem(it)
            card = lst.itemWidget(it)
            if card:
                self._on_card_menu(card)

    def _on_toggle_cmd(self, card, enabled):
        cmd = card.cmd
        self.sched._last[id(cmd)] = 0.0
        if enabled and not cmd.is_infinite:
            self.sched._remaining[id(cmd)] = cmd.count
        card.update_from_cmd()

    def _enable_cmd(self, cmd):
        cmd.enabled = True
        self.sched._last[id(cmd)] = 0.0
        if not cmd.is_infinite:
            self.sched._remaining[id(cmd)] = cmd.count
        card = self._card_of(cmd)
        if card:
            card.update_from_cmd()

    def _stop_cmd(self, cmd):
        cmd.enabled = False
        card = self._card_of(cmd)
        if card:
            card.update_from_cmd()

    def _make_can_obj(self, frame):
        obj = CAN_OBJ()
        obj.ID = frame.id
        obj.DataLen = len(frame.data)
        for i, b in enumerate(frame.data):
            obj.data[i] = b & 0xFF
        obj.RemoteFlag = 0
        obj.ExternFlag = 1 if frame.id > 0x7FF else 0
        obj.SendType = 0
        return obj

    def _tx_worker(self, ch):
        return self._txA if ch == CHAN_A else self._txB

    def _on_cmd_due(self, cmd):
        """调度到期：把该指令所有帧投递到对应通道发送线程。"""
        if not self._bus_open(cmd.channel):
            return
        worker = self._tx_worker(cmd.channel)
        if not worker:
            return
        total = len(cmd.frames)
        for i, f in enumerate(cmd.frames):
            worker.enqueue(self._make_can_obj(f), tag=cmd.name,
                           frame_idx=i, frame_total=total)

    def _send_once(self, cmd):
        if not self._bus_open(cmd.channel):
            QMessageBox.warning(self, "发送", "通道 %s 未打开" % cmd.channel)
            return
        worker = self._tx_worker(cmd.channel)
        if not worker:
            return
        for f in cmd.frames:
            worker.enqueue(self._make_can_obj(f), tag=cmd.name,
                           frame_idx=0, frame_total=len(cmd.frames))
        self._mon_append("CMD", "立即单发: %s" % cmd.name, 'info')

    def _toggle_running(self):
        if self._running:
            self._running = False
            self.sched.finish_silently()
            self.btn_run.setText("▶ 开始发送（锁定配置）")
            self._mon_append("SYSTEM", "定时发送已停止", 'info')
            self._refresh_lock()
        else:
            has = any(c.enabled for c in self._cmdsA + self._cmdsB)
            if not has:
                QMessageBox.information(self, "开始", "没有启用任何指令（打开某条指令的开关）")
                return
            if not self._bus_open(CHAN_A) and not self._bus_open(CHAN_B):
                QMessageBox.warning(self, "开始", "请先打开至少一个通道")
                return
            self._running = True
            self.sched.reset_runtime()
            self.btn_run.setText("⏹ 停止（解锁）")
            self._mon_append("SYSTEM", "定时发送已开始", 'info')
            self._refresh_lock()

    def _refresh_lock(self):
        enabled = not self._running
        # 运行锁：仅禁用编辑入口，保留查看/右键单发/停止能力
        for lst in (self.listA, self.listB):
            for i in range(lst.count()):
                it = lst.item(i)
                card = lst.itemWidget(it)
                if card:
                    card.sw.setEnabled(enabled)
        for btns in (getattr(self, 'toolBtnsA', None), getattr(self, 'toolBtnsB', None)):
            if btns:
                for b in btns.values():
                    b.setEnabled(enabled)
        self.btn_run.setEnabled(True)  # 始终允许停止

    # =========================================================
    # 监视流
    # =========================================================
    def _on_tx_result(self, channel, ok, code, tag, frame_idx, frame_total):
        if ok:
            self._tx_cnt[channel] += 1
            self._mon_append(channel, "TX OK  %s  (帧%d/%d)" % (tag, frame_idx + 1, frame_total), 'tx')
        else:
            self._err_cnt[channel] += 1
            self._mon_append(channel, "TX FAIL  %s  code=%s" % (tag, code), 'err')
        # 映射到卡片最近结果
        card = self._card_by_name(tag)
        if card:
            card.set_result(ok)
        self._refresh_stats()

    def _card_by_name(self, name):
        if not name:
            return None
        for lst in (self.listA, self.listB):
            for i in range(lst.count()):
                it = lst.item(i)
                if it.data(Qt.UserRole) and it.data(Qt.UserRole).name == name:
                    return lst.itemWidget(it)
        return None

    def _on_rx_frame(self, channel, fid, data):
        self._rx_cnt[channel] += 1
        hexs = ' '.join('%02X' % b for b in data)
        self._mon_append(channel, "RX  0x%X  %s" % (fid, hexs), 'rx')
        self._refresh_stats()

    def _mon_append(self, tag, msg, kind='info'):
        colors = {'tx': '#2f6fed', 'rx': '#0e9f6e', 'err': '#e5484d',
                  'info': '#7c8798', 'system': '#8b5cf6', 'CMD': '#f29400'}
        c = colors.get(kind, '#7c8798')
        self.mon.appendHtml('<span style="color:%s">[%s] %s</span> %s' %
                            (c, _now_ms(), tag, msg.replace('<', '&lt;')))

    def _refresh_stats(self):
        self.lb_stats.setText(
            "TX A %d | TX B %d | RX A %d | RX B %d | 错误 A %d | 错误 B %d" % (
                self._tx_cnt['A'], self._tx_cnt['B'],
                self._rx_cnt['A'], self._rx_cnt['B'],
                self._err_cnt['A'], self._err_cnt['B']))
        # 更新顶部总线卡片计数
        for ch, st in ((CHAN_A, self.busA_stat), (CHAN_B, self.busB_stat)):
            st.setText("波特率 500K   TX %d   RX %d   ERR %d" % (
                self._tx_cnt[ch], self._rx_cnt[ch], self._err_cnt[ch]))

    def _on_ui_tick(self):
        if not self._running:
            return
        self.sched.tick()
        for c in self.sched.take_just_finished():
            card = self._card_of(c)
            if card:
                card.cmd.enabled = False
                card.sw.setChecked(False)
                card.set_result(None)
                card.lb_result.setText("已完成")
                card.lb_result.setStyleSheet("font-size:10px; color:#0e9f6e; padding:0 6px; font-weight:600;")
                card.update_from_cmd()
            self._mon_append("SYSTEM", "指令 %s 已达发送次数，自动停止" % c.name, 'info')

    # =========================================================
    # 主题
    # =========================================================
    def _toggle_dark(self):
        self._dark = not self._dark
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(DARK_QSS if self._dark else LIGHT_QSS)
        self.mon.setStyleSheet(
            "font-family:'Cascadia Code','Consolas',monospace; font-size:11px;" +
            ("color:#1d2633; background:#fff; border:1px solid #e2e8f2; border-radius:8px;"
             if not self._dark else
             "color:#e8edf5; background:#161c26; border:1px solid #263141; border-radius:8px;"))
        self._rebuild_lists()

    # =========================================================
    # 导入/导出
    # =========================================================
    def _export_cfg_menu(self):
        menu = QMenu(self)
        a1 = QAction("JSON", menu)
        a1.triggered.connect(self._export_json)
        menu.addAction(a1)
        a2 = QAction("Excel", menu)
        a2.triggered.connect(self._export_excel)
        menu.addAction(a2)
        menu.exec_(QCursor.pos())

    def _import_cfg_menu(self):
        menu = QMenu(self)
        a1 = QAction("JSON", menu)
        a1.triggered.connect(self._import_json)
        menu.addAction(a1)
        a2 = QAction("Excel", menu)
        a2.triggered.connect(self._import_excel)
        menu.addAction(a2)
        menu.exec_(QCursor.pos())

    def _export_json(self):
        if self._running:
            QMessageBox.warning(self, "导出", "运行中禁止导出")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出配置", "can_cmds.json", "JSON (*.json)")
        if not path:
            return
        try:
            data = {'A': [c.to_dict() for c in self._cmdsA],
                    'B': [c.to_dict() for c in self._cmdsB]}
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._mon_append("SYSTEM", "已导出配置 %s" % path, 'info')
        except Exception as ex:
            QMessageBox.warning(self, "导出失败", str(ex))

    def _export_excel(self):
        if self._running:
            QMessageBox.warning(self, "导出", "运行中禁止导出")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出配置(Excel)", "can_cmds.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            for ch in (CHAN_A, CHAN_B):
                ws = wb.create_sheet(ch)
                ws.append(["名称", "间隔ms", "次数(0=无限)", "启用", "帧列表(每行: <ID hex> <数据 hex>)"])
                for c in self._cmds(ch):
                    lines = "\n".join("%X %s" % (f.id, ' '.join('%02X' % b for b in f.data))
                                      for f in c.frames)
                    ws.append([c.name, c.interval_ms, 0 if c.is_infinite else c.count,
                               "1" if c.enabled else "0", lines])
            if "Sheet" in wb.sheetnames:
                del wb["Sheet"]
            wb.save(path)
            self._mon_append("SYSTEM", "已导出 Excel %s" % path, 'info')
        except Exception as ex:
            QMessageBox.warning(self, "导出失败", str(ex))

    def _import_json(self):
        if self._running:
            QMessageBox.warning(self, "导入", "运行中禁止导入")
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            newA, newB = [], []
            if isinstance(data, dict):
                for d in data.get('A', []):
                    newA.append(CanCommand.from_dict(d))
                for d in data.get('B', []):
                    newB.append(CanCommand.from_dict(d))
            elif isinstance(data, list):
                for d in data:
                    c = CanCommand.from_dict(d)
                    (newA if c.channel == CHAN_A else newB).append(c)
            self._cmdsA, self._cmdsB = newA, newB
            self.sched.clear()
            self._rebuild_lists()
            self.sched.set_commands(self._cmdsA + self._cmdsB)
            self._mon_append("SYSTEM", "已导入 %s" % path, 'info')
        except Exception as ex:
            QMessageBox.warning(self, "导入失败", str(ex))

    def _import_excel(self):
        if self._running:
            QMessageBox.warning(self, "导入", "运行中禁止导入")
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            newA, newB = [], []
            for ch in (CHAN_A, CHAN_B):
                if ch not in wb.sheetnames:
                    continue
                ws = wb[ch]
                rows = list(ws.iter_rows(values_only=True))
                for r in rows[1:]:
                    if not r or not r[0]:
                        continue
                    name, interval, cnt, enabled, frames_txt = r[0], r[1], r[2], r[3], r[4]
                    frames = []
                    for ln in str(frames_txt or "").splitlines():
                        ln = ln.strip()
                        if not ln:
                            continue
                        parts = ln.split()
                        fid = int(parts[0], 16)
                        data = parse_hex_bytes(" ".join(parts[1:]))
                        frames.append(CanFrame(fid, data))
                    c = CanCommand(name or "导入", ch,
                                   int(interval or 500),
                                   INFINITE if (cnt is None or int(cnt or 0) <= 0) else int(cnt),
                                   bool(int(enabled or 0)), frames)
                    (newA if ch == CHAN_A else newB).append(c)
            self._cmdsA, self._cmdsB = newA, newB
            self.sched.clear()
            self._rebuild_lists()
            self.sched.set_commands(self._cmdsA + self._cmdsB)
            self._mon_append("SYSTEM", "已导入 Excel %s" % path, 'info')
        except Exception as ex:
            QMessageBox.warning(self, "导入失败", str(ex))

    def closeEvent(self, e):
        self.sched.finish_silently()
        for ch in (CHAN_A, CHAN_B):
            if self._bus_open(ch):
                self._close_bus(ch)
        super().closeEvent(e)
