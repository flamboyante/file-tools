# -*- coding: utf-8 -*-
"""A 方案 · qfluentwidgets 1.11.3 还原 v3 mockup。

════════════════════════════════════════════════════════════════
和 C（已删）相比，这里省掉的是"从零画一个控件"的部分：
  · 卡片底 + 投影     → ElevatedCardWidget
  · 开关 + 滑块动画   → SwitchButton
  · 按钮 + hover      → PushButton / PrimaryPushButton
  · 滚动容器          → ScrollArea / SmoothScrollArea
  · 主题切换          → setTheme()

但**不是零 QSS**：v3 里的胶囊（chip）、圆角徽章、状态点这些
qfluentwidgets 没有对应控件，仍然要用 QSS 描出来。
准确说法是"少 QSS"，不是"无 QSS"——这点在报告里如实写了。

════════════════════════════════════════════════════════════════
两个实测坑（1.11.3）
════════════════════════════════════════════════════════════════
① `setTheme()` **不管顶层 QDialog 的背景**，也不改已建 `ElevatedCardWidget`
   的底色（实测浅色建卡 #fafafa，切深色后仍是 #fafafa）。
   ⇒ 顶层用 `QPalette` 补，卡片用 `setBackgroundColor()` 显式指定。
   ⚠️ 顺序很重要：**先重建卡片，再上色**。反过来会被重建覆盖掉。

② `setBackgroundColor()` 走的是属性动画（`backgroundColorAni`），
   但实测立即 grab 也能拿到新色，不需要等动画。

数据与收发来自 uicmp.core —— 与 B 方案同源。
"""
import os
import sys
import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette, QFont
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                             QLabel, QFrame, QSizePolicy, QMessageBox)

from qfluentwidgets import (
    Theme, setTheme, setThemeColor,
    ElevatedCardWidget, CardWidget, SwitchButton,
    PrimaryPushButton, PushButton, TransparentToolButton,
    BodyLabel, StrongBodyLabel, CaptionLabel, SubtitleLabel, TitleLabel,
    ScrollArea, FluentIcon as FIF,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from uicmp import core

# ---------------------------------------------------------------- 视觉常量
# v3 mockup 的色值，浅/深两套（QSS 里用，qfluentwidgets 主题另管一部分）
C_BLUE = '#2f6fed'
C_BLUE_D = '#4c8dff'
C_PURPLE = '#8b5cf6'
C_PURPLE_D = '#a78bfa'
C_GREEN = '#0e9f6e'
C_GREEN_D = '#2fc48a'
C_RED = '#e5484d'
C_RED_D = '#f2555a'


def _chip_style(kind, dark):
    """胶囊样式（qfluentwidgets 没有对应控件，只能用 QSS）。"""
    pal = {
        'blue':   (C_BLUE, C_BLUE_D, '#e9f0ff', '#1b2a47'),
        'purple': (C_PURPLE, C_PURPLE_D, '#f0eafd', '#2b2044'),
        'green':  (C_GREEN, C_GREEN_D, '#e5f6ef', '#0f2e22'),
        'red':    (C_RED, C_RED_D, '#fdeaea', '#3a1a1d'),
        'gray':   ('#7c8798', '#8d99a8', '#e8edf3', '#252e3a'),
    }[kind]
    fg = pal[1] if dark else pal[0]
    bg = pal[3] if dark else pal[2]
    return ('QLabel{background:%s; color:%s; border-radius:11px;'
            'padding:3px 11px; font-size:11px;}' % (bg, fg))


def _badge_style(kind, dark):
    pal = {
        'ok':   (C_GREEN, C_GREEN_D, '#e5f6ef', '#0f2e22'),
        'run':  (C_BLUE, C_BLUE_D, '#e9f0ff', '#1b2a47'),
        'busy': ('#5b6b7b', '#9fb0bf', '#e8edf3', '#252e3a'),
        'err':  (C_RED, C_RED_D, '#fdeaea', '#3a1a1d'),
        'gray': ('#7c8798', '#8d99a8', '#e8edf3', '#252e3a'),
    }[kind]
    fg = pal[1] if dark else pal[0]
    bg = pal[3] if dark else pal[2]
    return ('QLabel{background:%s; color:%s; border-radius:11px;'
            'padding:2px 10px; font-size:10.5px; font-weight:600;}' % (bg, fg))


def chip(text, kind, dark):
    lb = QLabel(text)
    # ⚠️ 必须显式打开，否则 QSS 的 background 在 QLabel 上不绘制（只画文字）
    lb.setAttribute(Qt.WA_StyledBackground, True)
    lb.setStyleSheet(_chip_style(kind, dark))
    lb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lb


def badge(text, kind, dark):
    lb = QLabel(text)
    lb.setAttribute(Qt.WA_StyledBackground, True)
    lb.setStyleSheet(_badge_style(kind, dark))
    lb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lb


def ch_badge(ch, dark, size=34):
    """通道方块徽章（渐变底 + 白字）。"""
    lb = QLabel(ch)
    lb.setFixedSize(size, size)
    lb.setAlignment(Qt.AlignCenter)
    a, b = ((C_BLUE_D, C_BLUE) if ch == core.CHAN_A else (C_PURPLE_D, C_PURPLE))
    lb.setStyleSheet(
        'QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,'
        'stop:0 %s,stop:1 %s); color:#ffffff; border-radius:10px;'
        'font-size:%dpx; font-weight:800;}' % (a, b, int(size * 0.42)))
    return lb


# ================================================ 顶部总线卡片
class _BusCard(ElevatedCardWidget):
    """v3 顶部的总线卡：大徽章 + 名称/状态 + 波特率·TX·RX·错误 + 按钮 + 开关。"""

    def __init__(self, ch, dark=False, on_toggle=None, parent=None):
        super(_BusCard, self).__init__(parent)
        self.ch = ch
        self.dark = dark
        self.on_toggle = on_toggle

        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(12)
        h.addWidget(ch_badge(ch, dark, 38))

        col = QVBoxLayout()
        col.setSpacing(1)
        self.lbl_name = StrongBodyLabel('通道 %s' % ch)
        # qfluentwidgets 默认是 14px/12px，和 v3 的 14px/10.5px 不完全一致，显式对齐
        self.lbl_name.setStyleSheet('QLabel{font-size:14px;}')
        self.lbl_note = CaptionLabel('未连接')
        self.lbl_note.setStyleSheet('QLabel{font-size:10.5px;}')
        col.addWidget(self.lbl_name)
        col.addWidget(self.lbl_note)
        h.addLayout(col, 1)

        self.lbl_stat = QLabel('')
        h.addWidget(self.lbl_stat)

        self.btn = PushButton('打开设备')
        self.btn.clicked.connect(lambda: self._fire())
        h.addWidget(self.btn)

        self.sw = SwitchButton()
        self.sw.setOnText('')
        self.sw.setOffText('')
        self.sw.checkedChanged.connect(lambda _v: self._fire(silent=True))
        h.addWidget(self.sw)

    def _fire(self, silent=False):
        if self.on_toggle:
            self.on_toggle(self.ch, silent)

    def update_state(self, opened, note, baud, tx, rx, err, dark):
        self.dark = dark
        self.btn.setText('关闭设备' if opened else '打开设备')
        self.sw.blockSignals(True)
        self.sw.setChecked(bool(opened))
        self.sw.blockSignals(False)

        g = C_GREEN_D if dark else C_GREEN
        gray = '#8d99a8' if dark else '#7c8798'
        self.lbl_name.setText(
            '通道 %s <span style="color:%s;font-size:10.5px;font-weight:600">%s</span>'
            % (self.ch, g if opened else gray, '● 已开启' if opened else '○ 已关闭'))
        self.lbl_name.setTextFormat(Qt.RichText)
        self.lbl_note.setText(note or '')

        txc = (C_BLUE_D if dark else C_BLUE) if self.ch == core.CHAN_A \
            else (C_PURPLE_D if dark else C_PURPLE)
        self.lbl_stat.setText(
            '<span style="color:%s">波特率 <b>%s</b></span>&nbsp;&nbsp;&nbsp;'
            '<span style="color:%s">TX <b>%d</b></span>&nbsp;&nbsp;&nbsp;'
            '<span style="color:%s">RX <b>%d</b></span>&nbsp;&nbsp;&nbsp;'
            '<span style="color:%s">错误 <b>%d</b></span>'
            % (gray, baud, txc, tx, g, rx, C_RED_D if dark else C_RED, err))
        self.lbl_stat.setTextFormat(Qt.RichText)


# ================================================ 指令气泡卡
class _CmdCard(ElevatedCardWidget):
    """指令卡：徽章 + 名称/副标题 + 胶囊排 + badge + 开关 + chevron，可展开帧明细。"""

    ROW_H = 58
    FRAME_H = 24

    def __init__(self, cmd, ch, idx, dark=False, on_toggle=None, on_send=None,
                 on_pick=None, parent=None):
        super(_CmdCard, self).__init__(parent)
        self.cmd = cmd
        self.ch = ch
        self.idx = idx
        self.dark = dark
        self.on_toggle = on_toggle
        self.on_send = on_send
        self.on_pick = on_pick
        self._open = False
        self._sel = False
        self.on_resize = None

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 8, 14, 8)
        v.setSpacing(6)

        # ---- 主行 ----
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        h.addWidget(ch_badge(ch, dark, 34))

        col = QVBoxLayout()
        col.setSpacing(1)
        self.lbl_name = StrongBodyLabel(cmd.name)
        self.lbl_name.setStyleSheet('QLabel{font-size:13.5px;}')     # v3: .cmd-name
        self.lbl_sub = CaptionLabel('')
        self.lbl_sub.setStyleSheet('QLabel{font-size:10.5px;}')      # v3: .cmd-name .sub
        col.addWidget(self.lbl_name)
        col.addWidget(self.lbl_sub)
        h.addLayout(col, 1)

        self.chip_frames = chip('%d 帧' % len(cmd.frames), 'blue', dark)
        self.chip_intv = chip('⏱ %d ms' % cmd.interval_ms, 'gray', dark)
        cnt = '∞' if cmd.count <= 0 else str(cmd.count)
        self.chip_cnt = chip('⇉ %s' % cnt, 'gray', dark)
        h.addWidget(self.chip_frames)
        h.addWidget(self.chip_intv)
        h.addWidget(self.chip_cnt)

        self.lbl_state = CaptionLabel('')
        h.addWidget(self.lbl_state)

        self.lbl_badge = badge('停止', 'gray', dark)
        h.addWidget(self.lbl_badge)

        self.sw = SwitchButton()
        self.sw.setOnText('')
        self.sw.setOffText('')
        self.sw.setChecked(bool(cmd.enabled))
        self.sw.checkedChanged.connect(lambda _v: self._fire_toggle())
        h.addWidget(self.sw)

        self.chev = QLabel('▾')
        self.chev.setStyleSheet('QLabel{color:%s;font-size:12px;}'
                                % ('#8d99a8' if dark else '#7c8798'))
        self.chev.setCursor(Qt.PointingHandCursor)
        h.addWidget(self.chev)

        v.addWidget(row)

        # ---- 帧明细（默认隐藏）----
        self.detail = QFrame()
        self.detail.setVisible(False)
        dv = QVBoxLayout(self.detail)
        dv.setContentsMargins(44, 0, 0, 0)
        dv.setSpacing(2)
        for k, f in enumerate(cmd.frames):
            line = QLabel('#%d&nbsp;&nbsp;<b style="color:%s">0x%X</b>'
                          '&nbsp;&nbsp;<span style="color:#7c8798">%s</span>'
                          % (k + 1,
                             (C_BLUE_D if dark else C_BLUE) if ch == core.CHAN_A
                             else (C_PURPLE_D if dark else C_PURPLE),
                             f.id, ' '.join('%02X' % b for b in f.data)))
            line.setTextFormat(Qt.RichText)
            line.setStyleSheet('QLabel{font-family:Consolas,monospace;font-size:11px;'
                               'padding:2px 6px;}')
            dv.addWidget(line)
        self._detail_lines = dv
        v.addWidget(self.detail)

        self.setCursor(Qt.PointingHandCursor)

    # ------------------------------------------------ 交互
    def _fire_toggle(self):
        if self.on_toggle:
            self.on_toggle(self.idx)

    def mousePressEvent(self, e):
        if self.on_pick:
            self.on_pick(self.idx)
        super(_CmdCard, self).mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.set_open(not self._open)

    def set_open(self, on):
        self._open = bool(on)
        self.detail.setVisible(self._open)
        self.chev.setText('▴' if self._open else '▾')
        self.updateGeometry()
        if self.on_resize:
            self.on_resize()

    def sizeHint(self):
        from PyQt5.QtCore import QSize
        extra = (12 + len(self.cmd.frames) * self.FRAME_H) if self._open else 0
        return QSize(600, self.ROW_H + extra)

    def minimumSizeHint(self):
        from PyQt5.QtCore import QSize
        return self.sizeHint()

    def update_state(self, dark, selected=False):
        self.dark = dark
        self._sel = selected
        c = self.cmd
        self.lbl_name.setText(c.name)
        self.lbl_sub.setText('双击展开 · 右键更多 · 帧1 ID 0x%X' % c.frames[0].id
                             if c.frames else '')
        cnt = '∞' if c.count <= 0 else str(c.count)
        for w, txt, kind in ((self.chip_frames, '%d 帧' % len(c.frames), 'blue'),
                             (self.chip_intv, '⏱ %d ms' % c.interval_ms, 'gray'),
                             (self.chip_cnt, '⇉ %s' % cnt, 'gray')):
            w.setText(txt)
            w.setStyleSheet(_chip_style(kind, dark))

        ok = getattr(c, '_last_ok', None)
        if ok is True:
            self.lbl_state.setText('最近成功')
            self.lbl_state.setStyleSheet('QLabel{color:%s;font-size:11px;}'
                                         % (C_GREEN_D if dark else C_GREEN))
        elif ok is False:
            self.lbl_state.setText('TX 失败 · 总线错误')
            self.lbl_state.setStyleSheet('QLabel{color:%s;font-size:11px;}'
                                         % (C_RED_D if dark else C_RED))
        else:
            self.lbl_state.setText('')

        if c.enabled:
            self.lbl_badge.setText('运行中')
            self.lbl_badge.setStyleSheet(_badge_style('run', dark))
        else:
            self.lbl_badge.setText('停止')
            self.lbl_badge.setStyleSheet(_badge_style('gray', dark))

        self.sw.blockSignals(True)
        self.sw.setChecked(bool(c.enabled))
        self.sw.blockSignals(False)

        self.chev.setStyleSheet('QLabel{color:%s;font-size:12px;}'
                                % ('#8d99a8' if dark else '#7c8798'))
        # 帧明细配色随主题
        for k, lb in enumerate(
                [self._detail_lines.itemAt(i).widget()
                 for i in range(self._detail_lines.count())]):
            if lb is None or k >= len(c.frames):
                continue
            f = c.frames[k]
            lb.setText('#%d&nbsp;&nbsp;<b style="color:%s">0x%X</b>'
                       '&nbsp;&nbsp;<span style="color:%s">%s</span>'
                       % (k + 1,
                          (C_BLUE_D if dark else C_BLUE) if self.ch == core.CHAN_A
                          else (C_PURPLE_D if dark else C_PURPLE),
                          f.id, '#8d99a8' if dark else '#7c8798',
                          ' '.join('%02X' % b for b in f.data)))

        self.set_open(self._open)


# ================================================ 监视区一行
class _MonitorLine(QFrame):
    """v3 的 mline：左色条 + 时间 + 通道徽章 + 方向徽章 + 帧号 + ID + data。"""

    def __init__(self, m, dark=False, parent=None):
        super(_MonitorLine, self).__init__(parent)
        ch = m.get('ch', 'SYSTEM')
        d = (m.get('dir') or 'SYS').upper()
        accent = {'A': (C_BLUE_D if dark else C_BLUE),
                  'B': (C_PURPLE_D if dark else C_PURPLE)}.get(ch, '#8d99a8' if dark else '#7c8798')
        bg = '#1b2330' if dark else '#ffffff'
        bd = '#263141' if dark else '#e2e8f2'
        self.setStyleSheet(
            'QFrame{background:%s;border:1px solid %s;border-left:4px solid %s;'
            'border-radius:10px;}' % (bg, bd, accent))

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 12, 4)
        h.setSpacing(10)

        def mono(txt, color='#7c8798', bold=False, w=None):
            lb = QLabel(txt)
            lb.setStyleSheet('QLabel{border:none;background:transparent;color:%s;'
                             'font-family:Consolas,monospace;font-size:11.5px;%s}'
                             % (color, 'font-weight:700;' if bold else ''))
            if w:
                # min-width（和 v3 的 .m-time{min-width} 一致）：等宽字体保证列对齐，
                # 用 setFixedWidth 会把长一点的内容裁掉
                lb.setMinimumWidth(w)
            return lb

        # 时间列：必须放得下 '14:09:22.264'（12 字符 @ Consolas 11.5px ≈ 90px）
        h.addWidget(mono(m.get('time', ''), w=118))
        # 通道徽章：v3 是 padding 撑开的胶囊（宽度自适应），不能写死尺寸，
        # 否则圆角会把 "A" 挤成一个括号形状；SYSTEM 也需要更宽
        chip_ch = QLabel(ch)
        chip_ch.setAlignment(Qt.AlignCenter)
        chip_ch.setAttribute(Qt.WA_StyledBackground, True)
        chip_ch.setStyleSheet(
            'QLabel{background:%s;color:#ffffff;border-radius:8px;'
            'font-size:9px;font-weight:800;padding:1px 6px;}' % accent)
        h.addWidget(chip_ch)
        # 方向徽章
        dir_colors = {'TX': ('#e9f0ff', C_BLUE_D if dark else C_BLUE),
                      'RX': ('#0f2e22' if dark else '#e5f6ef', C_GREEN_D if dark else C_GREEN),
                      'ERR': ('#3a1a1d' if dark else '#fdeaea', C_RED_D if dark else C_RED),
                      'SYS': ('#252e3a' if dark else '#e8edf3', '#8d99a8' if dark else '#7c8798')}
        dbg, dfg = dir_colors.get(d, dir_colors['SYS'])
        chip_dir = QLabel(d)
        chip_dir.setAlignment(Qt.AlignCenter)
        chip_dir.setAttribute(Qt.WA_StyledBackground, True)
        chip_dir.setStyleSheet(
            'QLabel{background:%s;color:%s;border-radius:5px;font-size:9px;'
            'font-weight:800;padding:1px 6px;}' % (dbg, dfg))
        h.addWidget(chip_dir)

        if m.get('fno'):
            h.addWidget(mono(m['fno'], w=60))
        if m.get('id'):
            idc = {'TX': '#e8edf5' if dark else '#1d2633',
                   'RX': C_GREEN_D if dark else C_GREEN,
                   'ERR': C_RED_D if dark else C_RED,
                   'SYS': '#8d99a8' if dark else '#7c8798'}[d]
            h.addWidget(mono(m['id'], idc, True, w=120))
        h.addStretch(1)
        if m.get('data'):
            dcol = C_RED_D if (dark and d == 'ERR') else (C_RED if d == 'ERR'
                    else ('#8d99a8' if dark else '#7c8798'))
            lb = mono(m['data'], dcol)
            lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            h.addWidget(lb)


# ================================================ 统计卡
class _StatCard(ElevatedCardWidget):
    def __init__(self, label, value, kind, dark=False, parent=None):
        super(_StatCard, self).__init__(parent)
        self.kind = kind
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 6, 16, 6)
        v.setSpacing(0)
        self.lbl_n = QLabel(str(value))
        self.lbl_k = CaptionLabel(label)
        v.addWidget(self.lbl_n)
        v.addWidget(self.lbl_k)
        self.update_value(value, kind, dark)

    def update_value(self, value, kind, dark):
        col = {'blue': C_BLUE_D if dark else C_BLUE,
               'purple': C_PURPLE_D if dark else C_PURPLE,
               'green': C_GREEN_D if dark else C_GREEN,
               'red': C_RED_D if dark else C_RED}[kind]
        self.kind = kind
        self.lbl_n.setText(str(value))
        self.lbl_n.setStyleSheet('QLabel{color:%s;font-size:17px;font-weight:800;'
                                 'font-family:Consolas,monospace;}' % col)


# ================================================ A 方案主窗口
class AWindow(QDialog):
    """A 方案：qfluentwidgets 组合控件还原 v3。"""

    def __init__(self, parent=None, mode=core.Mode.AUTO):
        super(AWindow, self).__init__(parent)
        self.setWindowTitle('A 方案 · qfluentwidgets 还原 v3')
        self.resize(1280, 900)
        # ⚠️ 必须在创建任何子控件**之前**设字体。
        # qfluentwidgets 的 label 只设 pixelSize、不设 family，family 靠父控件继承；
        # 不设的话在中文 Windows 上会落到 SimSun（宋体）——
        # 而 v3 用的是 'Segoe UI','Microsoft YaHei'，两者观感完全不同。
        # 注意：q.setFontFamilies() 对此**无效**（实测仍为 SimSun），只能用 setFont。
        self.setFont(QFont('Microsoft YaHei UI'))

        self._dark = False
        self.tab = core.CHAN_A
        self.running = False
        self.paused = False
        self.filt = {'chan': {core.CHAN_A: True, core.CHAN_B: True},
                     'dir': {'TX': True, 'RX': True, 'ERR': True}}
        self.monitor = []
        self.buscount = {core.CHAN_A: [0, 0, 0], core.CHAN_B: [0, 0, 0]}
        self.stats = {'txA': 0, 'txB': 0, 'rx': 0, 'busy': 0, 'err': 0}
        self.busnote = {core.CHAN_A: '未连接', core.CHAN_B: '未连接'}
        self.sel = {core.CHAN_A: -1, core.CHAN_B: -1}
        self.cmds = {core.CHAN_A: [], core.CHAN_B: []}
        self._cards = []

        setThemeColor(C_BLUE)
        self._bus = core.CanBus(mode, self)
        self._bus.txResult.connect(self._on_tx)
        self._bus.rxFrame.connect(self._on_rx)
        self._bus.busState.connect(self._on_bus)

        self._build()
        self._load_case()
        self._apply_theme()

    # ------------------------------------------------------------ 布局
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        # ---- 顶栏 ----
        top = QHBoxLayout()
        top.setSpacing(8)
        ttl = TitleLabel('CAN 多指令定时发送')
        ttl.setStyleSheet('QLabel{font-size:17px;}')     # v3: .apptitle
        top.addWidget(ttl)
        self.pill_case = CaptionLabel('')
        top.addWidget(self.pill_case)
        top.addStretch(1)
        for t in ('导入 JSON', '导入 Excel', '导出配置'):
            b = PushButton(t)
            b.clicked.connect(lambda _=False, n=t: self._notimpl(n))
            top.addWidget(b)
        self.btn_run = PrimaryPushButton('▶ 开始发送（锁定配置）')
        self.btn_run.clicked.connect(self._toggle_run)
        top.addWidget(self.btn_run)
        self.btn_theme = PushButton('🌙 深色')
        self.btn_theme.clicked.connect(self._toggle_theme)
        top.addWidget(self.btn_theme)
        root.addLayout(top)

        # ---- 总线卡片 ----
        bus_box = CardWidget()
        bh = QHBoxLayout(bus_box)
        bh.setContentsMargins(14, 10, 14, 10)
        bh.setSpacing(14)
        self.bus_cards = {}
        for ch in core.CHANNELS:
            c = _BusCard(ch, self._dark, self._on_bus_toggle)
            self.bus_cards[ch] = c
            bh.addWidget(c, 1)
        root.addWidget(bus_box)

        # ---- Tab ----
        tb = QHBoxLayout()
        tb.setSpacing(6)
        self.tab_btns = {}
        for ch in core.CHANNELS:
            b = PushButton('通道 %s' % ch)
            b.setCheckable(True)
            b.setChecked(ch == self.tab)
            b.clicked.connect(lambda _=False, c=ch: self._switch_tab(c))
            self.tab_btns[ch] = b
            tb.addWidget(b)
        tb.addStretch(1)
        root.addLayout(tb)

        # ---- 编辑工具条 ----
        tools = QHBoxLayout()
        tools.setSpacing(6)
        b_add = PushButton(FIF.ADD, '添加指令')
        b_add.clicked.connect(self._add_cmd)
        b_del = PushButton(FIF.DELETE, '删除')
        b_del.clicked.connect(self._del_cmd)
        b_copy = PushButton('复制选中')
        b_copy.clicked.connect(self._copy_cmd)
        b_up = PushButton('↑')
        b_up.setFixedWidth(40)
        b_up.clicked.connect(lambda: self._move_cmd(-1))
        b_dn = PushButton('↓')
        b_dn.setFixedWidth(40)
        b_dn.clicked.connect(lambda: self._move_cmd(1))
        for b in (b_add, b_del, b_copy):
            tools.addWidget(b)
        tools.addWidget(b_up)
        tools.addWidget(b_dn)
        self.lbl_hint = CaptionLabel('间隔 ≥10ms · 双击行展开 · 右键更多')
        tools.addStretch(1)
        tools.addWidget(self.lbl_hint)
        root.addLayout(tools)

        # ---- 指令列表 ----
        self.cmd_host = QWidget()
        self.cmd_v = QVBoxLayout(self.cmd_host)
        self.cmd_v.setContentsMargins(2, 2, 2, 2)
        self.cmd_v.setSpacing(10)
        self.cmd_v.addStretch(1)
        self.cmd_sa = ScrollArea()
        self.cmd_sa.setWidgetResizable(True)
        self.cmd_sa.setWidget(self.cmd_host)
        # 不占 flex：高度按内容算（_fit_cmd_height），剩余空间沉到底部，
        # 这样和 v3 网页的「自然高度」观感一致，中间不会留一大块空白
        self.cmd_sa.setFixedHeight(160)
        root.addWidget(self.cmd_sa)

        # ---- 监视区 ----
        mon_box = CardWidget()
        mv = QVBoxLayout(mon_box)
        mv.setContentsMargins(14, 10, 14, 12)
        mv.setSpacing(8)
        mh = QHBoxLayout()
        mh.addWidget(StrongBodyLabel('收发监视流'))
        self.lbl_monhint = CaptionLabel('· 每帧一条气泡 · 最新在上')
        mh.addWidget(self.lbl_monhint)
        mh.addStretch(1)
        self.filt_btns = {}
        for grp, items in (('chan', [(core.CHAN_A, '通道 A'), (core.CHAN_B, '通道 B')]),
                           ('dir', [('TX', 'TX'), ('RX', 'RX'), ('ERR', 'ERR')])):
            for val, text in items:
                b = PushButton(text)
                b.setCheckable(True)
                b.setChecked(True)
                b.clicked.connect(lambda _=False, g=grp, v=val: self._toggle_filter(g, v))
                self.filt_btns[(grp, val)] = b
                mh.addWidget(b)
        b_pause = PushButton('暂停')
        b_pause.setCheckable(True)
        b_pause.clicked.connect(lambda: self._set_pause(b_pause.isChecked()))
        b_clear = PushButton('清空')
        b_clear.clicked.connect(self._clear_monitor)
        mh.addWidget(b_pause)
        mh.addWidget(b_clear)
        mv.addLayout(mh)

        self.mon_host = QWidget()
        self.mon_v = QVBoxLayout(self.mon_host)
        self.mon_v.setContentsMargins(2, 2, 2, 2)
        self.mon_v.setSpacing(6)
        self.mon_v.addStretch(1)
        self.mon_sa = ScrollArea()
        self.mon_sa.setWidgetResizable(True)
        self.mon_sa.setWidget(self.mon_host)
        self.mon_sa.setFixedHeight(240)
        mv.addWidget(self.mon_sa)
        root.addWidget(mon_box)

        # ---- 统计卡 ----
        st = QHBoxLayout()
        st.setSpacing(10)
        self.stat_cards = {}
        for key, label, kind in (('txA', 'TX · A', 'blue'), ('txB', 'TX · B', 'purple'),
                                 ('rx', 'RX 总数', 'green'), ('busy', '应答中', 'blue'),
                                 ('err', '发送错误', 'red')):
            c = _StatCard(label, 0, kind, self._dark)
            self.stat_cards[key] = c
            st.addWidget(c)
        st.addStretch(1)
        root.addLayout(st)
        root.addStretch(1)          # 剩余空间全部沉到底部

    # ------------------------------------------------------------ 数据
    def _load_case(self):
        a, b = core.load_case()
        self.cmds[core.CHAN_A] = a
        self.cmds[core.CHAN_B] = b
        self.pill_case.setText('用例：%d + %d 条' % (len(a), len(b)))
        self._refresh_cmds()

    def _refresh_cmds(self):
        while self.cmd_v.count() > 1:
            it = self.cmd_v.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cards = []
        for i, c in enumerate(self.cmds[self.tab]):
            card = _CmdCard(c, self.tab, i, self._dark,
                            on_toggle=self._on_cmd_toggle,
                            on_send=self._send,
                            on_pick=self._pick)
            card.on_resize = self._fit_cmd_height
            card.update_state(self._dark, self.sel[self.tab] == i)
            self.cmd_v.insertWidget(self.cmd_v.count() - 1, card)
            self._cards.append(card)
        for ch, btn in self.tab_btns.items():
            btn.setText('通道 %s（%d 条）' % (ch, len(self.cmds[ch])))
            btn.setChecked(ch == self.tab)
        self._fit_cmd_height()

    def _fix_fonts(self):
        """把落到 SimSun 的控件字体族拨正。

        qfluentwidgets 的 label 在构造时 `QFont()` **只设了 pixelSize**，
        family 取的是 `QApplication.font()` —— 中文 Windows 上是 SimSun（宋体）。
        所以 `q.setFontFamilies()` / `self.setFont()` 都改不动它们（实测），
        只能在控件建好之后逐个 setFont。
        """
        for w in self.findChildren(QWidget):
            try:
                fam = w.font().family()
            except Exception:
                continue
            if fam in ('SimSun', 'NSimSun', '宋体', ''):
                f = w.font()
                f.setFamily('Microsoft YaHei UI')
                w.setFont(f)

    def _fit_cmd_height(self):
        """指令区高度按内容算：卡片数 x 行高 + 展开的帧明细高度。

        上限 430（再多就内部滚动），下限 160。这样内容少时不会留大片空白，
        内容多时也不会把监视区挤没。
        """
        h = 18
        for card in self._cards:
            h += 58 + 10
            if card._open:
                h += 12 + len(card.cmd.frames) * 24
        self.cmd_sa.setFixedHeight(max(160, min(430, h)))

    # ------------------------------------------------------------ 主题
    def _apply_theme(self):
        """顺序很关键：**先重建组件、再统一上色**。

        实测：`setTheme()` 不改变已建 `ElevatedCardWidget` 的底色；
        而 `setBackgroundColor()` 有效。若先上色后重建，会被重建覆盖。
        """
        dark = self._dark
        setTheme(Theme.DARK if dark else Theme.LIGHT)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor('#0d1117' if dark else '#eef2f9'))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # 1) 重建（新组件按当前主题初始化内部配色）
        self._refresh_cmds()
        self._refresh_monitor()
        self._refresh_stats()

        # 2) 统一上色
        bg = QColor('#161c26' if dark else '#ffffff')
        for cls in (CardWidget, ElevatedCardWidget):
            for w in self.findChildren(cls):
                try:
                    w.backgroundColorAni.stop()
                except Exception:
                    pass
                try:
                    w.setBackgroundColor(bg)
                except Exception:
                    pass

        # 3) 顶部/总线状态
        for ch in core.CHANNELS:
            self.bus_cards[ch].update_state(
                self._bus.is_open(ch), self.busnote[ch], core.BAUD_LABEL,
                self.buscount[ch][0], self.buscount[ch][1], self.buscount[ch][2], dark)
        self.btn_theme.setText('☀ 浅色' if dark else '🌙 深色')
        self.setStyleSheet('AWindow{background:%s;}' % ('#0d1117' if dark else '#eef2f9'))
        self._fix_fonts()          # 每次重建后都要拨一次

    def _toggle_theme(self):
        self._dark = not self._dark
        self._apply_theme()

    def _notimpl(self, name):
        QMessageBox.information(self, name, '%s · 本次对比只做最小交互，这一项未接入' % name)

    # ------------------------------------------------------------ 交互
    def _switch_tab(self, ch):
        self.tab = ch
        self._refresh_cmds()

    def _on_bus_toggle(self, ch, silent=False):
        if self._bus.is_open(ch):
            self._bus.close_channel(ch)
        else:
            self._bus.open_channel(ch)

    def _on_cmd_toggle(self, idx):
        lst = self.cmds[self.tab]
        if 0 <= idx < len(lst):
            lst[idx].enabled = not lst[idx].enabled
            if idx < len(self._cards):
                self._cards[idx].update_state(self._dark, self.sel[self.tab] == idx)

    def _pick(self, idx):
        self.sel[self.tab] = idx
        for i, c in enumerate(self._cards):
            c.update_state(self._dark, i == idx)

    def _send(self, idx):
        lst = self.cmds[self.tab]
        if 0 <= idx < len(lst):
            self._bus.send_once(lst[idx])

    def _add_cmd(self):
        from WorkClass.CANCommandScheduler import CanCommand, CanFrame
        ch = self.tab
        cmd = CanCommand('新指令 %d' % (len(self.cmds[ch]) + 1), ch, 500, -1, False,
                         [CanFrame(0x31801, [0x00, 0x5A, 0x5A])])
        self.cmds[ch].append(cmd)
        self._apply_theme()

    def _del_cmd(self):
        ch, i = self.tab, self.sel[self.tab]
        if 0 <= i < len(self.cmds[ch]):
            self.cmds[ch].pop(i)
            self.sel[ch] = -1
            self._apply_theme()
        else:
            QMessageBox.information(self, '删除', '请先单击选中一条指令')

    def _copy_cmd(self):
        ch, i = self.tab, self.sel[self.tab]
        if 0 <= i < len(self.cmds[ch]):
            c = self.cmds[ch][i].copy()
            c.name = c.name + ' 副本'
            self.cmds[ch].insert(i + 1, c)
            self._apply_theme()
        else:
            QMessageBox.information(self, '复制', '请先单击选中一条指令')

    def _move_cmd(self, d):
        ch, i = self.tab, self.sel[self.tab]
        j = i + d
        lst = self.cmds[ch]
        if 0 <= i < len(lst) and 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self.sel[ch] = j
            self._apply_theme()

    def _toggle_run(self):
        self.running = not self.running
        self.btn_run.setText('⏹ 停止（解锁）' if self.running
                             else '▶ 开始发送（锁定配置）')

    def _set_pause(self, on):
        self.paused = bool(on)

    def _toggle_filter(self, grp, val):
        self.filt[grp][val] = not self.filt[grp][val]
        self._refresh_monitor()

    def _clear_monitor(self):
        self.monitor = []
        self._refresh_monitor()

    # ------------------------------------------------------------ 监视
    def _add_line(self, ch, direction, fno='', fid='', data=''):
        m = {'time': time.strftime('%H:%M:%S.') + ('%03d' % (int(time.time() * 1000) % 1000)),
             'ch': ch, 'dir': direction, 'fno': fno, 'id': fid, 'data': data}
        self.monitor.append(m)
        if len(self.monitor) > 300:
            self.monitor.pop(0)
        if self.paused:
            return
        if ch != 'SYSTEM':
            if not self.filt['chan'].get(ch, True):
                return
            if not self.filt['dir'].get(direction, True):
                return
        # 最新在最上面
        w = _MonitorLine(m, self._dark)
        self.mon_v.insertWidget(0, w)
        while self.mon_v.count() > 302:
            it = self.mon_v.takeAt(self.mon_v.count() - 2)
            if it and it.widget():
                it.widget().setParent(None)

    def _refresh_monitor(self):
        while self.mon_v.count() > 1:
            it = self.mon_v.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for m in reversed(self.monitor[-300:]):
            ch = m['ch']
            if ch != 'SYSTEM':
                if not self.filt['chan'].get(ch, True):
                    continue
                if not self.filt['dir'].get(m['dir'], True):
                    continue
            self.mon_v.insertWidget(self.mon_v.count() - 1, _MonitorLine(m, self._dark))

    def _refresh_stats(self):
        for key, card in self.stat_cards.items():
            card.update_value(self.stats[key], card.kind, self._dark)

    # ------------------------------------------------------------ 回调
    def _sync_bus_card(self, ch):
        """只刷新总线卡片，不写监视日志（TX/RX 高频调用它）。"""
        self.bus_cards[ch].update_state(
            self._bus.is_open(ch), self.busnote[ch], core.BAUD_LABEL,
            self.buscount[ch][0], self.buscount[ch][1], self.buscount[ch][2], self._dark)

    def _on_bus(self, ch, opened, msg):
        self.busnote[ch] = msg
        self._sync_bus_card(ch)
        self._add_line('SYSTEM', 'SYS', '', '', '通道 %s：%s' % (ch, msg))

    def _on_tx(self, ch, ok, tag, idx, total):
        tx, rx, err = self.buscount[ch]
        self.buscount[ch] = [tx + (1 if ok else 0), rx, err + (0 if ok else 1)]
        if ok:
            self.stats['txA' if ch == core.CHAN_A else 'txB'] += 1
        else:
            self.stats['err'] += 1
        fid, fdata = '', ''
        for i, c in enumerate(self.cmds.get(ch) or []):
            if c.name == tag:
                c._last_ok = bool(ok)
                if idx < len(c.frames):
                    fid = '0x%X' % c.frames[idx].id
                    fdata = ' '.join('%02X' % b for b in c.frames[idx].data)
                break
        self._sync_bus_card(ch)
        self._refresh_stats()
        self._add_line(ch, 'TX' if ok else 'ERR', '帧%d/%d' % (idx + 1, total),
                       fid, fdata if ok else '发送失败 · 底层返回码非 1')
        if ch == self.tab:
            self._refresh_cmds()

    def _on_rx(self, ch, fid, data):
        tx, rx, err = self.buscount[ch]
        self.buscount[ch] = [tx, rx + 1, err]
        self.stats['rx'] += 1
        self._sync_bus_card(ch)
        self._refresh_stats()
        self._add_line(ch, 'RX', '应答', '0x%X' % fid,
                       ' '.join('%02X' % b for b in data))

    def closeEvent(self, e):
        try:
            self._bus.shutdown()
        except Exception:
            pass
        super(AWindow, self).closeEvent(e)


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = AWindow()
    w.show()
    sys.exit(app.exec_())
