# -*- coding: utf-8 -*-
"""transfer_app · 文件传输页（单发 = 批量的 N=1 特例，取代旧
FlashDownWindow + BatchFlashDownWindow 两个窗口）。

布局：
  ConnectionBar（连接条，与 console 共用组件）
  任务区：拖拽/添加 → 表格（文件·大小·Flash·目标·状态·进度·删除）
  工具条：添加 · 删除未开始 · 失败策略 · 开始 · 暂停 · 继续 · 停止
  总进度 + 日志

目标映射（复用+补强，自旧 BatchFlashDownWindow 原样搬入）：
  flash: 基带=0xFB 基带2=0x9B SC=0xFA
  mem:   37 个部件/Flash 位
"""
import os

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QBrush, QColor, QPainter
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QComboBox,
                             QProgressBar, QPushButton, QHeaderView,
                             QAbstractItemView, QFrame, QStyledItemDelegate)

from qfluentwidgets import (PushButton, PrimaryPushButton, CheckBox,
                            CaptionLabel, FluentIcon as FIF)

from uicmp.guicore.transfer_queue import (TransferQueue, TransferTask,
                                          T_PENDING, T_RUNNING, T_DONE,
                                          T_FAILED, T_SKIPPED,
                                          POLICY_SKIP, POLICY_ABORT)
from uicmp.guiwidgets import theme
from uicmp.guiwidgets.common import ConnectionBar

FLASH_MAP = {
    "基带": 0xFB,
    "基带2": 0x9B,
    "SC": 0xFA,
}

MEM_MAP = {
    "PLP0 Flash0(默认)": 0x05,
    "PLP1 Flash0(默认)": 0x07,
    "BBPS OS Flash0(默认)": 0x12,
    "BBPS APP Flash0(默认)": 0x02,
    "BBPS CFG Flash0(默认)": 0x22,
    "BBPKA OS Flash0(默认)": 0x13,
    "BBPKA APP Flash0(默认)": 0x03,
    "BBPKA CFG Flash0(默认)": 0x23,
    "SCP OS Flash0(默认)": 0x10,
    "SCP APP Flash0(默认)": 0x00,
    "SCP CFG Flash0(默认)": 0x20,
    "BMU UPDATE": 0x06,
    "BMU DIR": 0x36,
    "BMU GOLDEN": 0x26,
    "BMU IAP": 0x16,
    "PLP0 Flash1": 0x45,
    "PLP0 Flash2": 0x85,
    "PLP1 Flash1": 0x47,
    "PLP1 Flash2": 0x87,
    "BBPS OS Flash1": 0x52,
    "BBPS APP Flash1": 0x42,
    "BBPS CFG Flash1": 0x62,
    "BBPS OS Flash2": 0x92,
    "BBPS APP Flash2": 0x82,
    "BBPS CFG Flash2": 0xA2,
    "BBPKA OS Flash1": 0x53,
    "BBPKA APP Flash1": 0x43,
    "BBPKA CFG Flash1": 0x63,
    "BBPKA OS Flash2": 0x93,
    "BBPKA APP Flash2": 0x83,
    "BBPKA CFG Flash2": 0xA3,
    "SCP OS Flash1": 0x50,
    "SCP APP Flash1": 0x40,
    "SCP CFG Flash1": 0x60,
    "SCP OS Flash2": 0x90,
    "SCP ATA2": 0x70,
    "BBPS EXC": 0x32,
    "BBPKA EXC": 0x33,
}

STATUS_TEXT = {T_PENDING: '待执行', T_RUNNING: '执行中', T_DONE: '已完成',
               T_FAILED: '失败', T_SKIPPED: '已跳过'}

# 状态语义色统一在 theme（STATE_STRIPE 亮色画条 / STATE_TEXT 深色着色文字）。
# 任务状态码 → theme 色板键的映射：
STATE_KEY = {T_PENDING: 'pending', T_RUNNING: 'running', T_DONE: 'done',
             T_FAILED: 'failed', T_SKIPPED: 'skipped'}

# 列：0=文件 1=大小 2=Flash 3=目标 4=状态 5=进度 6=删除
COL_FILE, COL_SIZE, COL_FLASH, COL_MEM, COL_STATUS, COL_PROGRESS, COL_DEL = range(7)


class _StatusDelegate(QStyledItemDelegate):
    """状态列：默认绘制右侧文字，左缘画 3px 圆角色条（颜色即状态）。

    ⚠️ 为什么用 delegate 而不是列内 widget/item 背景：
    ① item.setBackground 会被 QSS ::item 规则静默忽略
    ② cellWidget 会被 ::item 的 padding 榨成 0 宽（10px 列 - 20px padding）
    delegate 的 paint 不受这两者影响，是在 opt.rect 上直接画（实测结论）。
    """

    def __init__(self, get_dark, parent=None):
        super(_StatusDelegate, self).__init__(parent)
        self._get_dark = get_dark

    def paint(self, painter, opt, index):
        super(_StatusDelegate, self).paint(painter, opt, index)
        status = index.data(Qt.UserRole)
        if not status:
            return
        color = QColor(theme.state_stripe(status, self._get_dark()))
        r = opt.rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        bar = QRect(r.left() + 3, r.top() + 11, 3, r.height() - 22)
        painter.drawRoundedRect(bar, 1.5, 1.5)
        painter.restore()


class _DropArea(QFrame):
    """空态：虚线拖拽区 + 引导文案（无任务时显示，替代空表格）。"""

    def __init__(self, parent=None):
        super(_DropArea, self).__init__(parent)
        self.setObjectName('dropArea')
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        t = QLabel('拖入固件文件，或点上方「添加」')
        t.setObjectName('dropTitle')
        t.setAlignment(Qt.AlignCenter)
        h = QLabel('每一行选择 Flash 与目标；单发 = 只放一个文件')
        h.setObjectName('dropHint')
        h.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addSpacing(4)
        lay.addWidget(h)
        lay.addStretch(1)


class TransferApp(QDialog):
    def __init__(self, parent=None, link=None):
        super(TransferApp, self).__init__(parent)
        self._dark = False
        self._locked = False               # 全局锁定（禁编辑待执行任务）
        self.setObjectName('TransferApp')
        self.setWindowTitle('文件传输 · gui-ng')
        self.resize(980, 640)
        self.setAcceptDrops(True)

        from uicmp.guicore.serial_link import SerialLink
        self.link = link if link is not None else SerialLink()
        self.queue = TransferQueue(self.link)

        self._build()
        self.apply_theme(False)

    # ------------------------------------------------------------ UI
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(theme.GAP)

        self.conn = ConnectionBar(self.link, dark=False)
        self.link.opened.connect(
            lambda: self.log('[√] 已连接'))
        self.link.closed.connect(
            lambda: self.log('[×] 已断开'))
        self.link.error.connect(self.log)
        v.addLayout(self._wrap(self.conn))

        # ---- 工具条：左（动作组） ··· 右（策略）
        tools = QHBoxLayout()
        tools.setSpacing(theme.GAP_SM)
        self.btn_add = PushButton(FIF.ADD, '添加')
        self.btn_del_pending = PushButton('删除未开始')
        self.btn_start = PrimaryPushButton(FIF.PLAY, '开始')
        self.btn_pause = PushButton(FIF.PAUSE, '暂停')
        self.btn_resume = PushButton(FIF.PLAY_SOLID, '继续')
        self.btn_stop = PushButton(FIF.CLOSE, '停止')
        self.btn_lock = PushButton('锁定')
        for w in (self.btn_add, self.btn_del_pending,
                  self.btn_start, self.btn_pause, self.btn_resume,
                  self.btn_stop, self.btn_lock):
            tools.addWidget(w)
        tools.addStretch(1)
        self.chk_abort = CheckBox('失败即中止')
        self.chk_abort.setToolTip('不勾选：失败跳过继续下一个（旧行为）')
        tools.addWidget(self.chk_abort)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(False)
        v.addLayout(tools)

        # ---- 任务区：空态（拖拽引导） / 表格 互斥切换
        self.drop_area = _DropArea()
        v.addWidget(self.drop_area, 3)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ['文件', '大小', 'Flash', '目标', '状态', '进度', ''])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setFixedHeight(36)
        self.table.setItemDelegateForColumn(
            COL_STATUS, _StatusDelegate(lambda: self._dark))
        self.table.horizontalHeader().setSectionResizeMode(
            COL_FILE, QHeaderView.Stretch)
        for col, w in ((COL_SIZE, 90), (COL_FLASH, 110), (COL_MEM, 190),
                       (COL_STATUS, 96), (COL_PROGRESS, 130), (COL_DEL, 76)):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, w)
        self.table.setShowGrid(True)   # 细浅网格线（gridline-color 在 QSS），利于多列对行
        self.table.setVisible(False)
        v.addWidget(self.table, 3)

        # ---- 总进度 + 日志
        self.total_bar = QProgressBar()
        self.total_bar.setRange(0, 100)
        self.total_bar.setFormat('总进度 %p%')
        v.addWidget(self.total_bar, 0)

        self.log_view = self._make_log()
        v.addWidget(self.log_view, 1)
        self.log('提示：拖入固件文件或点「添加」；单发 = 只加一个任务')

        # ---- 信号
        self.btn_add.clicked.connect(self._pick_files)
        self.btn_del_pending.clicked.connect(self._del_pending)
        self.btn_start.clicked.connect(self._start)
        self.btn_pause.clicked.connect(self.queue.pause)
        self.btn_resume.clicked.connect(self.queue.resume)
        self.btn_stop.clicked.connect(self.queue.cancel)
        self.btn_lock.clicked.connect(self._toggle_lock)
        self.queue.task_changed.connect(self._on_task_changed)
        self.queue.queue_finished.connect(self._on_queue_finished)
        self.queue.queue_cancelled.connect(
            lambda: self.log('队列已取消'))

    def _wrap(self, w):
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w, 1)
        return h

    def _make_log(self):
        from PyQt5.QtWidgets import QTextEdit
        t = QTextEdit()
        t.setReadOnly(True)
        return t

    # ------------------------------------------------------------ 任务编辑
    def _pick_files(self):
        from PyQt5.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, '选择固件文件')
        self.add_files(paths)

    def add_files(self, paths):
        for p in paths:
            if not os.path.isfile(p):
                continue
            self.queue.tasks.append(TransferTask(
                file_path=p, total=os.path.getsize(p),
                flash_value=FLASH_MAP['基带'], mem_value=MEM_MAP['BMU UPDATE']))
        self._refresh_table()

    def _del_pending(self):
        self.queue.tasks[:] = [t for t in self.queue.tasks
                               if t.status != T_PENDING]
        self._refresh_table()

    def _toggle_lock(self):
        self._locked = not self._locked
        self.btn_lock.setText('解锁' if self._locked else '锁定')
        # 激活态：锁定后按钮变主色底（"点了之后有变化"的明确反馈）
        if self._locked:
            self.btn_lock.setStyleSheet(theme.primary_active_qss(self._dark))
        else:
            self.btn_lock.setStyleSheet('')
        self._refresh_table()

    # ------------------------------------------------------------ 调度
    def _start(self):
        pending = [t for t in self.queue.tasks if t.status == T_PENDING]
        if not pending:
            self.log('[!] 没有待执行任务')
            return
        if not self.link.is_open:
            self.log('[!] 链路未打开')
            return
        policy = POLICY_ABORT if self.chk_abort.isChecked() else POLICY_SKIP
        self.queue.start(pending, policy=policy)
        self._set_running_ui(True)
        self.log('队列启动：%d 个任务（失败策略=%s）'
                 % (len(pending), '中止' if policy == POLICY_ABORT else '跳过'))

    def _set_running_ui(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(running)
        self.btn_stop.setEnabled(running)
        self.btn_add.setEnabled(not running)
        self.btn_del_pending.setEnabled(not running)
        self.btn_lock.setEnabled(not running)

    def _on_task_changed(self, idx):
        if idx < 0:
            self._refresh_table()
        else:
            self._render_row(idx)
        self._update_total()

    def _on_queue_finished(self, summary):
        self._set_running_ui(False)
        self._refresh_table()
        self.log('[√] 队列结束：' + summary)

    # ------------------------------------------------------------ 表格
    def _refresh_table(self):
        tasks = self.queue.tasks
        self.table.setRowCount(len(tasks))
        for i, t in enumerate(tasks):
            self._render_row(i)
        self._update_total()
        # 空态切换：无任务显示拖拽引导，有任务显示表格
        self.drop_area.setVisible(not tasks)
        self.table.setVisible(bool(tasks))

    def _render_row(self, row):
        if row >= self.table.rowCount():
            return
        t = self.queue.tasks[row]
        editable = t.status == T_PENDING and not self._locked

        def item(text, tip=''):
            it = QTableWidgetItem(text)
            if tip:
                it.setToolTip(tip)
            return it

        self.table.setItem(row, COL_FILE,
                           item(os.path.basename(t.file_path), t.file_path))
        self.table.setItem(row, COL_SIZE, item(self._fmt(t.total)))
        status_item = item(STATUS_TEXT.get(t.status, t.status))
        status_item.setForeground(QColor(
            theme.state_text(STATE_KEY.get(t.status, 'pending'), self._dark)))
        status_item.setData(Qt.UserRole, STATE_KEY.get(t.status, 'pending'))
        self.table.setItem(row, COL_STATUS, status_item)

        flash_combo = QComboBox()
        flash_combo.addItems(FLASH_MAP.keys())
        flash_combo.setEnabled(editable)
        flash_combo.setStyleSheet(theme.combo_qss(self._dark))
        flash_combo.currentTextChanged.connect(
            lambda key, r=row: self._set_flash(r, key))
        self.table.setCellWidget(row, COL_FLASH, flash_combo)
        # 选中当前值
        for key, val in FLASH_MAP.items():
            if val == t.flash_value:
                flash_combo.setCurrentText(key)
                break

        mem_combo = QComboBox()
        mem_combo.addItems(MEM_MAP.keys())
        mem_combo.setEnabled(editable)
        mem_combo.setStyleSheet(theme.combo_qss(self._dark))
        mem_combo.currentTextChanged.connect(
            lambda key, r=row: self._set_mem(r, key))
        self.table.setCellWidget(row, COL_MEM, mem_combo)
        for key, val in MEM_MAP.items():
            if val == t.mem_value:
                mem_combo.setCurrentText(key)
                break

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        pct = int(t.transferred * 100 / t.total) if t.total else 0
        bar.setValue(pct)
        bar.setStyleSheet(theme.progress_qss(self._dark, height=8))
        self.table.setCellWidget(row, COL_PROGRESS, bar)

        del_btn = QPushButton('删除')
        del_btn.setEnabled(editable)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(theme.table_button_qss(self._dark))
        del_btn.clicked.connect(lambda checked=False, r=row: self._del_row(r))
        self.table.setCellWidget(row, COL_DEL, del_btn)

        if t.error:
            self.table.item(row, COL_STATUS).setToolTip(t.error)

    def _set_flash(self, row, key):
        if 0 <= row < len(self.queue.tasks):
            self.queue.tasks[row].flash_value = FLASH_MAP[key]

    def _set_mem(self, row, key):
        if 0 <= row < len(self.queue.tasks):
            self.queue.tasks[row].mem_value = MEM_MAP[key]

    def _del_row(self, row):
        if 0 <= row < len(self.queue.tasks):
            del self.queue.tasks[row]
            self._refresh_table()

    def _update_total(self):
        tasks = self.queue.tasks
        total = sum(t.total for t in tasks)
        done = sum(t.transferred for t in tasks if t.status != T_FAILED)
        self.total_bar.setValue(int(done * 100 / total) if total else 0)

    @staticmethod
    def _fmt(n):
        for unit in ('B', 'KB', 'MB', 'GB'):
            if n < 1024:
                return '%.1f %s' % (n, unit) if unit != 'B' else '%d B' % n
            n /= 1024.0
        return '%.1f TB' % n

    # ------------------------------------------------------------ 日志 / 拖拽
    def log(self, text):
        self.log_view.append(text)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_files([u.toLocalFile() for u in e.mimeData().urls()
                        if os.path.isfile(u.toLocalFile())])

    # ------------------------------------------------------------ 主题
    def apply_theme(self, dark):
        """⚠️ 约定：任何控件重建之后都要重调本函数。
        表格单元格内的 combo/进度条/按钮在 _refresh_table 重建时按当时
        主题上色——所以切主题必须重刷表格，否则行内控件不跟随。"""
        self._dark = dark
        theme.apply_theme(self, dark)
        self.conn.set_dark(dark)
        self.table.setStyleSheet(
            theme.table_qss(dark) + theme.scrollbar_qss(dark))
        self.drop_area.setStyleSheet(theme.drop_area_qss(dark))
        self.log_view.setStyleSheet(theme.log_qss(dark))
        self.total_bar.setStyleSheet(theme.progress_qss(dark, height=16))
        self._refresh_table()
        theme.fix_fonts(self)

    def toggle_theme(self):
        self.apply_theme(not self._dark)

    def closeEvent(self, e):
        self.queue.cancel()
        self.link.close()
        super(TransferApp, self).closeEvent(e)
