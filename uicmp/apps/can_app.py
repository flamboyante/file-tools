# -*- coding: utf-8 -*-
"""can_app · CAN 指令台（表格版）。

布局（自上而下）：
  总线区：A / B 两张卡（开关 + 状态 + TX/RX/ERR 统计）
  工具条：添加 复制 删除 上移 下移 预设 导入 导出 · 通道筛选 · 主题
  命令表：开关 | 名称 | 通道 | ID | 数据(多帧显示 n 帧 ▸) | 间隔 | 次数 | 状态 | 单发
          —— 双击行展开/折叠帧明细子行
  总控：开始发送（锁定配置）/ 停止 + 启用条数
  监视：TX 蓝 / RX 绿 / ERR 红 + 毫秒时间戳，可按通道与方向过滤

颜色约定（沿用 gui-ng 已定稿的语义）：
  通道 A = 蓝 chip / 通道 B = 紫 chip（v3 mockup 的通道配色）
  状态色条 = theme.STATE_STRIPE（颜色即状态，与 transfer 页同一套）
  监视日志：TX 主色蓝 / RX 绿 / ERR 红 / 时间戳 次级灰
"""
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QTextCharFormat
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QTextEdit, QLabel, QPushButton, QFrame, QSpinBox,
                             QSizePolicy, QMessageBox)

from qfluentwidgets import (PrimaryPushButton, CheckBox, ComboBox,
                            SwitchButton, TransparentToolButton,
                            FluentIcon as FIF)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from uicmp.guicore.can_session import CanSession, Mode, CHAN_A, CHAN_B
from uicmp.guicore.can_commands import CanFrame, PRESETS_A, PRESETS_B
from uicmp.guiwidgets import theme
from uicmp.guiwidgets.common import StatusDelegate

# 列：0=开关 1=名称 2=通道 3=ID 4=数据 5=间隔 6=次数 7=状态 8=单发
(COL_SW, COL_NAME, COL_CH, COL_ID, COL_DATA, COL_INTV,
 COL_CNT, COL_ST, COL_SEND) = range(9)
COL_COUNT = 9

MON_MAX_BLOCKS = 1200
MON_TRIM_TO = 900


def _now():
    import time
    t = time.time()
    lt = time.localtime(t)
    return '%02d:%02d:%02d.%03d' % (lt.tm_hour, lt.tm_min, lt.tm_sec,
                                    int((t - int(t)) * 1000))


def _fmt_id(fid):
    return '0x%08X' % (fid & 0x1FFFFFFF)


def _fmt_data(frames):
    if not frames:
        return '—'
    if len(frames) == 1:
        return ' '.join('%02X' % b for b in frames[0].data[:8])
    total = sum(len(f.data) for f in frames)
    return '%dB / %d 帧' % (total, len(frames))


class CanApp(QDialog):
    """CAN 指令台。session 可注入（测试用模拟模式）。"""

    def __init__(self, parent=None, session=None):
        super(CanApp, self).__init__(parent)
        self.session = session if session is not None else CanSession(mode=Mode.AUTO)
        self._dark = False
        self._expanded = set()          # 展开帧明细的指令 id
        self._selected = None           # 当前选中指令
        self._cur_ch = CHAN_A           # 当前通道 Tab（一次只看一个通道）
        self._mon_paused = False
        self.setObjectName('CanApp')
        self.setWindowTitle('CAN 指令台 · gui-ng')
        self.resize(980, 760)
        self._build()
        self.apply_theme(False)

    # ------------------------------------------------------------ UI
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(theme.GAP)

        # ---- 总线区（A / B 两张卡）
        bus = QHBoxLayout()
        bus.setSpacing(theme.GAP)
        self.bus = {}
        for ch, kind in ((CHAN_A, 'blue'), (CHAN_B, 'purple')):
            self.bus[ch] = self._make_bus_card(ch, kind)
            bus.addWidget(self.bus[ch], 1)
        v.addLayout(bus)

        # ---- 工具条
        tools = QHBoxLayout()
        tools.setSpacing(theme.GAP_SM)
        self.btn_add = QPushButton('添加')
        self.btn_copy = QPushButton('复制')
        self.btn_del = QPushButton('删除')
        self.btn_up = QPushButton('↑')
        self.btn_down = QPushButton('↓')
        self.combo_preset = ComboBox()
        self.combo_preset.setFixedWidth(150)
        self.combo_preset.addItems(['预设指令 ▾'] +
                                   [c.name for c in PRESETS_A] +
                                   [c.name for c in PRESETS_B])
        self.btn_import = QPushButton('导入')
        self.btn_export = QPushButton('导出')
        for w in (self.btn_add, self.btn_copy, self.btn_del,
                  self.btn_up, self.btn_down, self.combo_preset,
                  self.btn_import, self.btn_export):
            tools.addWidget(w, 0)
        tools.addStretch(1)
        self.btn_theme = TransparentToolButton(FIF.CONSTRACT)
        self.btn_theme.setToolTip('浅/深主题')
        tools.addWidget(self.btn_theme, 0)
        v.addLayout(tools)

        # ---- 通道 Tab（v3：一次只看一个通道，不是并排两张卡）
        tab = QHBoxLayout()
        tab.setSpacing(6)
        self.tab_btn = {}
        for ch in (CHAN_A, CHAN_B):
            b = QPushButton('通道 %s' % ch)
            b.setFixedHeight(28)
            b.clicked.connect(lambda _c=False, c=ch: self._switch_tab(c))
            self.tab_btn[ch] = b
            tab.addWidget(b, 0)
        tab.addStretch(1)
        self.lb_lock = QLabel('')      # 运行锁提示条（v3 的 lockVeil）
        self.lb_lock.setAlignment(Qt.AlignCenter)
        tab.addWidget(self.lb_lock, 1)
        v.addLayout(tab)

        # ---- 命令表
        self.table = QTableWidget(0, COL_COUNT)
        self.table.setHorizontalHeaderLabels(
            ['', '名称', '通道', 'ID', '数据', '间隔', '次数', '状态', ''])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.horizontalHeader().setFixedHeight(34)
        self.table.setItemDelegateForColumn(
            COL_ST, StatusDelegate(lambda: self._dark))
        self.table.horizontalHeader().setSectionResizeMode(
            COL_NAME, QHeaderView.Stretch)
        for col, w in ((COL_SW, 46), (COL_CH, 54), (COL_ID, 104),
                       (COL_DATA, 168), (COL_INTV, 68), (COL_CNT, 56),
                       (COL_ST, 108), (COL_SEND, 62)):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, w)
        self.table.setShowGrid(True)
        v.addWidget(self.table, 3)

        # ---- 总控
        run = QHBoxLayout()
        run.setSpacing(theme.GAP_SM)
        self.btn_run = PrimaryPushButton('▶ 开始发送（锁定配置）')
        self.btn_run.setFixedHeight(32)
        self.btn_stop = QPushButton('■ 停止')
        run.addWidget(self.btn_run, 0)
        run.addWidget(self.btn_stop, 0)
        run.addStretch(1)
        self.lb_info = QLabel('启用 0 条')
        run.addWidget(self.lb_info, 0)
        v.addLayout(run)

        # ---- 监视（v3：通道/方向是按钮组，可同时开；不是下拉）
        mon_row = QHBoxLayout()
        mon_row.setSpacing(6)
        mon_row.addWidget(self._label('监视'), 0)
        self.fbtn_ch = {}
        for ch, kind in ((CHAN_A, 'blue'), (CHAN_B, 'purple')):
            b = QPushButton('通道 %s' % ch)
            b.setCheckable(True)
            b.setChecked(True)
            b.setFixedHeight(26)
            b.setFixedWidth(76)
            b.clicked.connect(self._refresh_mon_filter)
            self.fbtn_ch[ch] = b
            mon_row.addWidget(b, 0)
        self.fbtn_kind = {}
        for k in ('TX', 'RX', 'ERR'):
            b = QPushButton(k)
            b.setCheckable(True)
            b.setChecked(True)
            b.setFixedHeight(26)
            b.setFixedWidth(56)
            b.clicked.connect(self._refresh_mon_filter)
            self.fbtn_kind[k] = b
            mon_row.addWidget(b, 0)
        mon_row.addStretch(1)
        self.btn_pause_mon = QPushButton('暂停')
        self.btn_clear_mon = QPushButton('清空')
        mon_row.addWidget(self.btn_pause_mon, 0)
        mon_row.addWidget(self.btn_clear_mon, 0)
        v.addLayout(mon_row)

        self.mon = QTextEdit()
        self.mon.setReadOnly(True)
        v.addWidget(self.mon, 1)

        # ---- 底部统计条（v3 bottombar）：TX·A / TX·B / RX 总数 / 应答中 / 错误 + 图例
        v.addLayout(self._make_bottombar())

        self._wire()

    def _make_bottombar(self):
        """底部统计卡 + 色系图例（TX/RX/ERR 统一放这里，不放总线卡内）。"""
        row = QHBoxLayout()
        row.setSpacing(8)
        self.stat_cards = {}
        self._stat_specs = [
            ('txA', 'TX · A', 'running'), ('txB', 'TX · B', 'busy'),
            ('rx', 'RX 总数', 'done'), ('busy', '应答中', 'running'),
            ('err', '发送错误', 'failed'),
        ]
        for key, label, kind in self._stat_specs:
            card = self._make_stat_card(label, kind)
            self.stat_cards[key] = card
            row.addWidget(card, 0)
        row.addStretch(1)

        legend = QHBoxLayout()
        legend.setSpacing(10)
        for text, kind in (('通道 A', 'running'), ('通道 B', 'busy'),
                           ('发送/运行', 'running'), ('接收/成功', 'done'),
                           ('错误/失败', 'failed')):
            dot = QLabel('●')
            dot.setStyleSheet('color: %s;' % theme.state_stripe(kind, self._dark))
            lb = QLabel(text)
            lb.setStyleSheet('font-size: 11px; color: %s;'
                             % (theme.C_TEXT_SUB_D if self._dark
                                else theme.C_TEXT_SUB))
            h = QHBoxLayout()
            h.setSpacing(4)
            h.addWidget(dot, 0)
            h.addWidget(lb, 0)
            box = self._hbox(h)
            legend.addWidget(box, 0)
        row.addLayout(legend)
        return row

    def _make_stat_card(self, label, kind):
        """统计卡：大数字（状态色）+ 小标签。"""
        card = QFrame()
        card.setObjectName('statCard')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(0)
        n = QLabel('0')
        n.setAlignment(Qt.AlignCenter)
        n.setStyleSheet('font-size: 17px; font-weight: 600; color: %s;'
                        % theme.state_stripe(kind, self._dark))
        k = QLabel(label)
        k.setAlignment(Qt.AlignCenter)
        k.setStyleSheet('font-size: 11px; color: %s;'
                        % (theme.C_TEXT_SUB_D if self._dark else theme.C_TEXT_SUB))
        lay.addWidget(n)
        lay.addWidget(k)
        card._num = n
        card._kind = kind
        return card

    def _hbox(self, layout):
        from PyQt5.QtWidgets import QWidget
        box = QWidget()
        box.setLayout(layout)
        return box

    def _switch_tab(self, ch):
        """切换通道 Tab（v3：一次只看一个通道）。"""
        self._cur_ch = ch
        self._selected = None
        self._refresh_table()

    def _refresh_mon_filter(self):
        """过滤条件变化时清屏（当前视图只显示符合条件的新日志）。"""
        self.mon.clear()

    def _label(self, text):
        lb = QLabel(text)
        lb.setStyleSheet('font-weight: 500;')
        return lb

    def _make_bus_card(self, ch, kind):
        """总线卡：通道徽章 + 开关按钮 + 状态徽章 + 统计。"""
        card = QFrame()
        card.setObjectName('busCard')
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        chip = theme.chip('通道 %s' % ch, kind, self._dark)
        lay.addWidget(chip, 0)

        lb_baud = QLabel('500K')
        lb_baud.setStyleSheet('color: %s;' % (theme.C_TEXT_SUB_D if self._dark
                                              else theme.C_TEXT_SUB))
        lay.addWidget(lb_baud, 0)

        btn = PrimaryPushButton('打开')
        btn.setFixedSize(76, 30)
        lay.addWidget(btn, 0)

        badge = theme.badge('未连接', 'gray', self._dark)
        lay.addWidget(badge, 0)

        lay.addStretch(1)
        # ⚠️ TX/RX/ERR 不放在这里——按 v3 设计统一收进底部 bottombar 统计卡
        card._chip = chip
        card._btn = btn
        card._badge = badge
        btn.clicked.connect(lambda: self._toggle_bus(ch))
        return card

    def _wire(self):
        s = self.session
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_add.clicked.connect(self._add)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_del.clicked.connect(self._delete)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.combo_preset.currentTextChanged.connect(self._add_preset)
        self.btn_import.clicked.connect(self._import)
        self.btn_export.clicked.connect(self._export)
        self.btn_run.clicked.connect(self._toggle_run)
        self.btn_stop.clicked.connect(self.session.stop_sending)
        self.btn_clear_mon.clicked.connect(self.mon.clear)
        self.btn_pause_mon.clicked.connect(self._toggle_pause_mon)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(self._on_dbl)
        self.table.cellClicked.connect(self._on_cell_click)

        s.txResult.connect(self._on_tx)
        s.rxFrame.connect(self._on_rx)
        s.busState.connect(self._on_bus_state)
        s.commandsChanged.connect(self._refresh_table)
        s.runStateChanged.connect(self._on_run_state)
        s.commandFinished.connect(
            lambda cmd: self._mon('ERR' if False else 'SYS', '指令完成：%s' % cmd.name))

        self._refresh_table()
        self._mon('SYS', '提示：打开通道 → 启用指令 → 开始发送；双击行看帧明细')

    # ------------------------------------------------------------ 总线
    def _toggle_bus(self, ch):
        s = self.session
        if s.is_open(ch):
            s.close_channel(ch)
        else:
            s.open_channel(ch)

    def _on_bus_state(self, ch, opened, msg):
        card = self.bus[ch]
        # 重建徽章与按钮态
        kind = 'ok' if opened else 'gray'
        new_badge = theme.badge('已连接' if opened else '未连接', kind, self._dark)
        lay = card.layout()
        lay.replaceWidget(card._badge, new_badge)
        card._badge.deleteLater()
        card._badge = new_badge

        card._btn.setText('关闭' if opened else '打开')
        if opened:
            card._btn.setStyleSheet(theme.primary_tint_qss(self._dark))
        else:
            card._btn.setStyleSheet('')
        self._mon('SYS', '通道 %s：%s' % (ch, msg))
        self._refresh_stats()

    def _refresh_stats(self):
        """刷新底部统计卡（TX·A / TX·B / RX 总数 / 应答中 / 发送错误）。"""
        a = self.session.stats(CHAN_A)
        b = self.session.stats(CHAN_B)
        vals = {'txA': a['tx'], 'txB': b['tx'],
                'rx': a['rx'] + b['rx'],
                'busy': 1 if self.session.is_running and self.session.active_count() else 0,
                'err': a['err'] + b['err']}
        for key, card in self.stat_cards.items():
            card._num.setText(str(vals.get(key, 0)))

    # ------------------------------------------------------------ 表格
    def _visible_cmds(self):
        """只显示当前 Tab 通道的指令（v3：通道是 Tab，不是并列筛选）。"""
        return list(self.session.commands(self._cur_ch))

    def _toggle_pause_mon(self):
        """暂停/继续刷新监视流（暂停期间只丢弃显示，收发仍在跑）。"""
        self._mon_paused = not self._mon_paused
        self.btn_pause_mon.setText('继续' if self._mon_paused else '暂停')
        self.btn_pause_mon.setStyleSheet(
            theme.primary_active_qss(self._dark) if self._mon_paused
            else theme.outline_button_qss(self._dark))

    def _refresh_table(self):
        cmds = self._visible_cmds()
        # 展开行会占额外行：先算总行数
        total = len(cmds) + sum(1 for c in cmds if id(c) in self._expanded)
        # ⚠️ 必须先清零再设行数：行复用时旧 cellWidget（开关/单发按钮）会
        # 残留在变成「展开行」的行上（实测：展开行里挂着上一轮的按钮）
        self.table.setRowCount(0)
        self.table.setRowCount(total)
        self.table.setUpdatesEnabled(False)
        r = 0
        for c in cmds:
            self._render_row(r, c)
            r += 1
            if id(c) in self._expanded:
                self._render_frames_row(r, c)
                r += 1
        self.table.setUpdatesEnabled(True)
        self._refresh_tabs()
        self._refresh_info()

    def _render_row(self, row, c):
        t = self.table

        # 开关
        sw = SwitchButton()
        sw.setOnText('')       # ⚠️ 1.11.x 默认带 On/Off 文本，必须关掉
        sw.setOffText('')
        sw.setChecked(c.enabled)
        sw.setEnabled(not self.session.is_running)
        sw.checkedChanged.connect(lambda on, cmd=c: self._on_switch(cmd, on))
        t.setCellWidget(row, COL_SW, self._wrap(sw))

        name = QTableWidgetItem(c.name)
        if self._selected is c:
            name.setBackground(QColor(theme.C_PRIMARY_BG_D if self._dark
                                      else theme.C_PRIMARY_BG))
        t.setItem(row, COL_NAME, name)

        ch_item = QTableWidgetItem(c.channel)
        ch_item.setForeground(QColor(theme.C_PRIMARY_D if self._dark else theme.C_PRIMARY)
                              if c.channel == CHAN_A else
                              QColor(theme.C_PURPLE_D if self._dark else theme.C_PURPLE))
        t.setItem(row, COL_CH, ch_item)

        t.setItem(row, COL_ID, QTableWidgetItem(_fmt_id(c.frames[0].id) if c.frames else '—'))
        t.setItem(row, COL_DATA, QTableWidgetItem(_fmt_data(c.frames)))
        t.setItem(row, COL_INTV, QTableWidgetItem('%dms' % c.interval_ms))
        t.setItem(row, COL_CNT, QTableWidgetItem('∞' if c.is_infinite else str(c.count)))

        # 状态（色条 kind + 文字）
        kind, text = self._state_of(c)
        st = QTableWidgetItem(text)
        st.setForeground(QColor(theme.state_text(kind, self._dark)))
        st.setData(Qt.UserRole, kind)
        t.setItem(row, COL_ST, st)

        btn = QPushButton('单发')
        btn.setStyleSheet(theme.table_action_qss(self._dark))
        btn.setEnabled(not self.session.is_running)
        btn.clicked.connect(lambda _c=False, cmd=c: self._send_once(cmd))
        t.setCellWidget(row, COL_SEND, btn)

    def _render_frames_row(self, row, c):
        """帧明细子行：合并单元格显示每一帧的 ID + 数据。"""
        t = self.table
        lines = []
        for i, f in enumerate(c.frames):
            lines.append('帧%d  %s  %s' % (i + 1, _fmt_id(f.id),
                                           ' '.join('%02X' % b for b in f.data)))
        text = '\n'.join(lines) if lines else '（无帧）'
        item = QTableWidgetItem(text)
        item.setForeground(QColor(theme.C_TEXT_SUB_D if self._dark
                                  else theme.C_TEXT_SUB))
        item.setFlags(Qt.ItemIsEnabled)
        t.setItem(row, COL_NAME, item)
        t.setSpan(row, COL_NAME, 1, COL_COUNT - COL_NAME)
        t.setRowHeight(row, max(24, 18 * len(lines) + 8))

    def _state_of(self, c):
        """(kind, 文字) —— 运行中优先，其次失败，再按启用与否。"""
        if self.session.is_running and c.enabled:
            rem = self.session.remaining_of(c)
            if rem is not None:
                return 'running', '发送中 · 剩 %d' % rem
            return 'running', '发送中'
        if not c.frames:
            return 'failed', '无帧'
        return ('busy', '已启用') if c.enabled else ('pending', '待发')

    def _wrap(self, w):
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setAlignment(Qt.AlignCenter)
        h.addWidget(w)
        from PyQt5.QtWidgets import QWidget
        box = QWidget()
        box.setLayout(h)
        return box

    def _refresh_tabs(self):
        """Tab 上带条数 + 选中态（v3：通道 A 3 条 / 通道 B 2 条）。"""
        for ch, b in self.tab_btn.items():
            n = len(self.session.commands(ch))
            b.setText('通道 %s · %d 条' % (ch, n))
            b.setStyleSheet(theme.primary_active_qss(self._dark)
                            if ch == self._cur_ch
                            else theme.outline_button_qss(self._dark))

    def _refresh_info(self):
        n = self.session.active_count()
        self.lb_info.setText('启用 %d 条' % n)

    # ------------------------------------------------------------ 操作
    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            self._selected = None
            return
        row = items[0].row()
        cmds = self._visible_cmds()
        # 展开行会占行号：只映射主行
        idx = 0
        for c in cmds:
            if idx == row:
                self._selected = c
                return
            idx += 1
            if id(c) in self._expanded:
                idx += 1
        self._selected = None

    def _on_dbl(self, row, _col):
        cmds = self._visible_cmds()
        idx = 0
        for c in cmds:
            if idx == row:
                if id(c) in self._expanded:
                    self._expanded.discard(id(c))
                else:
                    self._expanded.add(id(c))
                self._refresh_table()
                return
            idx += 1
            if id(c) in self._expanded:
                idx += 1

    def _on_cell_click(self, row, col):
        if col == COL_SEND:
            return      # 按钮自处理
        self._on_select()

    def _on_switch(self, cmd, on):
        self.session.set_enabled(cmd, bool(on))
        self._refresh_table()

    def _send_once(self, cmd):
        if self.session.send_once(cmd):
            self._mon('SYS', '单发：%s（%d 帧）' % (cmd.name, len(cmd.frames)))

    def _add(self):
        c = self.session.add_command(self._filter_channel())
        self._edit_command(c)

    def _copy(self):
        c = self._selected
        if c is None:
            return
        from uicmp.guicore.can_commands import CanCommand
        copy = CanCommand.from_dict(c.to_dict())
        copy.name = c.name + ' 副本'
        copy.enabled = False
        self.session.add_command(c.channel, copy)

    def _delete(self):
        c = self._selected
        if c is None:
            return
        if QMessageBox.question(self, '删除', '删除指令「%s」？' % c.name,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        self.session.remove_command(c.channel, c)
        self._selected = None

    def _move(self, d):
        c = self._selected
        if c is not None:
            self.session.move_command(c.channel, c, d)

    def _filter_channel(self):
        return self._cur_ch

    def _add_preset(self, name):
        if not name or name.startswith('预设指令'):
            return
        src = PRESETS_A + PRESETS_B
        for c in src:
            if c.name == name:
                ch = self._filter_channel()
                new = c.copy()
                new.channel = ch
                new.enabled = False
                self.session.add_command(ch, new)
                break
        self.combo_preset.setCurrentIndex(0)

    def _edit_command(self, c):
        """最小编辑：名称 / 间隔 / 次数 / 帧数据（一行 hex）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle('编辑指令')
        lay = QVBoxLayout(dlg)
        from PyQt5.QtWidgets import QLineEdit, QFormLayout
        form = QFormLayout()
        e_name = QLineEdit(c.name)
        e_int = QSpinBox()
        e_int.setRange(10, 600000)
        e_int.setValue(c.interval_ms)
        e_cnt = QSpinBox()
        e_cnt.setRange(-1, 100000)
        e_cnt.setValue(c.count)
        e_cnt.setSpecialValueText('∞')
        e_frames = QLineEdit(_fmt_data(c.frames))
        form.addRow('名称', e_name)
        form.addRow('间隔 (ms)', e_int)
        form.addRow('次数 (-1=∞)', e_cnt)
        form.addRow('帧数据 (hex)', e_frames)
        lay.addLayout(form)
        row = QHBoxLayout()
        ok = PrimaryPushButton('确定')
        cancel = QPushButton('取消')
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(cancel, 0)
        row.addWidget(ok, 0)
        lay.addLayout(row)
        if dlg.exec_() == QDialog.Accepted:
            c.name = e_name.text().strip() or c.name
            c.interval_ms = e_int.value()
            c.count = -1 if e_cnt.value() < 0 else e_cnt.value()
            text = e_frames.text().strip()
            if text:
                from uicmp.guicore.can_commands import parse_hex_bytes
                data = parse_hex_bytes(text)
                if data:
                    fid = c.frames[0].id if c.frames else 0x100
                    c.frames = [CanFrame(fid, data[:8])]
            self.session.commandsChanged.emit()

    def _export(self):
        import json
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, '导出指令配置', '',
                                              'JSON (*.json)')
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.session.serialize(), f, ensure_ascii=False, indent=2)
        self._mon('SYS', '已导出：%s' % os.path.basename(path))

    def _import(self):
        import json
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, '导入指令配置', '',
                                              'JSON (*.json)')
        if not path:
            return
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.session.deserialize(data)
        self._mon('SYS', '已导入：%s' % os.path.basename(path))

    # ------------------------------------------------------------ 运行
    def _toggle_run(self):
        if self.session.is_running:
            self.session.stop_sending()
            return
        ok, msg = self.session.start_sending()
        if not ok:
            QMessageBox.warning(self, '开始发送', msg)
            return
        self._mon('SYS', '定时发送已开始')

    def _on_run_state(self, on):
        if on:
            self.btn_run.setText('⏹ 发送中（已锁定）')
            self.btn_run.setStyleSheet(theme.primary_active_qss(self._dark))
            self.lb_lock.setText('● 运行中 — 指令配置已锁定（查看/单发仍可用）')
        else:
            self.btn_run.setText('▶ 开始发送（锁定配置）')
            self.btn_run.setStyleSheet('')
            self.lb_lock.setText('')
            self._mon('SYS', '定时发送已停止')
        self.lb_lock.setStyleSheet(
            'background: %s; color: %s; border-radius: 6px; padding: 4px 10px;'
            'font-weight: 600;'
            % (theme.C_PRIMARY_BG_D if self._dark else theme.C_PRIMARY_BG,
               theme.C_PRIMARY_D if self._dark else theme.C_PRIMARY)
            if on else '')
        for w in (self.btn_add, self.btn_copy, self.btn_del,
                  self.btn_up, self.btn_down, self.btn_import):
            w.setEnabled(not on)
        self._refresh_table()
        self._refresh_stats()

    # ------------------------------------------------------------ 监视
    def _mon(self, kind, msg):
        """kind：'TX-A' / 'RX-B' / 'ERR' / 'SYS'（SYS=系统提示，始终显示）。"""
        if self._mon_paused:
            return
        if kind.startswith(('TX-', 'RX-')):
            ch = kind[-1]
            if not self.fbtn_ch.get(ch) or not self.fbtn_ch[ch].isChecked():
                return
            if kind.startswith('TX-') and not self.fbtn_kind['TX'].isChecked():
                return
            if kind.startswith('RX-') and not self.fbtn_kind['RX'].isChecked():
                return
        elif kind == 'ERR' and not self.fbtn_kind['ERR'].isChecked():
            return

        if kind.startswith('TX'):
            color = 'running'
        elif kind.startswith('RX'):
            color = 'done'
        elif kind == 'ERR':
            color = 'failed'
        else:
            color = 'pending'

        cursor = self.mon.textCursor()
        cursor.movePosition(cursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme.state_text(color, self._dark)))
        cursor.setCharFormat(fmt)     # 每次显式设置，防格式残留（console 踩过）
        cursor.insertText('%s  %-6s %s\n' % (_now(), kind, msg))
        self._trim_mon()
        self.mon.moveCursor(self.mon.textCursor().End)

    def _trim_mon(self):
        doc = self.mon.document()
        if doc.blockCount() > MON_MAX_BLOCKS:
            c = self.mon.textCursor()
            c.movePosition(c.Start)
            c.movePosition(c.Down, c.KeepAnchor, MON_MAX_BLOCKS - MON_TRIM_TO)
            c.removeSelectedText()

    def _on_tx(self, ch, ok, tag, idx, total):
        if ok:
            self._mon('TX-%s' % ch, '%s  (%d/%d)' % (tag or '(未命名)', idx + 1, total))
        else:
            self._mon('ERR', 'TX %s 失败 (帧 %d/%d)' % (tag or '?', idx + 1, total))
        self._refresh_stats()

    def _on_rx(self, ch, fid, data):
        self._mon('RX-%s' % ch, '%s  %s' % (_fmt_id(fid),
                                            ' '.join('%02X' % b for b in data)))
        self._refresh_stats()

    # ------------------------------------------------------------ 主题
    def toggle_theme(self):
        self._dark = not self._dark
        self.apply_theme(self._dark)

    def apply_theme(self, dark):
        """⚠️ 约定：任何控件重建之后都要重调本函数。"""
        self._dark = dark
        theme.apply_theme(self, dark)
        self.table.setStyleSheet(
            theme.table_qss(dark) + theme.scrollbar_qss(dark))
        self.mon.setStyleSheet(
            theme.log_qss(dark, mono=True) + theme.scrollbar_qss(dark))
        qss = theme.outline_button_qss(dark)
        for b in (self.btn_add, self.btn_copy, self.btn_del, self.btn_up,
                  self.btn_down, self.btn_import, self.btn_export,
                  self.btn_stop, self.btn_clear_mon):
            b.setStyleSheet(qss)
        # 过滤按钮组（勾选=主色激活，未勾选=描边）
        for b in list(self.fbtn_ch.values()) + list(self.fbtn_kind.values()):
            b.setStyleSheet(theme.primary_active_qss(dark) if b.isChecked()
                            else qss)
        self.btn_pause_mon.setStyleSheet(
            theme.primary_active_qss(dark) if self._mon_paused else qss)
        # 统计卡数字色（状态语义色随主题）
        for key, card in self.stat_cards.items():
            card._num.setStyleSheet(
                'font-size: 17px; font-weight: 600; color: %s;'
                % theme.state_stripe(card._kind, dark))
        if self.session.is_running:
            self.btn_run.setStyleSheet(theme.primary_active_qss(dark))
        # 总线卡：重建通道徽章（颜色随主题）
        for ch, kind in ((CHAN_A, 'blue'), (CHAN_B, 'purple')):
            card = self.bus[ch]
            old = card._chip
            new = theme.chip('通道 %s' % ch, kind, dark)
            card.layout().replaceWidget(old, new)
            old.deleteLater()
            card._chip = new
            if self.session.is_open(ch):
                card._btn.setStyleSheet(theme.primary_tint_qss(dark))
        self._refresh_table()
        theme.fix_fonts(self)

    # ------------------------------------------------------------ 生命周期
    def closeEvent(self, e):
        self.session.shutdown()
        super(CanApp, self).closeEvent(e)
