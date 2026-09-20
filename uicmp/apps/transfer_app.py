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

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QComboBox,
                             QProgressBar, QPushButton, QHeaderView,
                             QAbstractItemView)

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

COL_FILE, COL_SIZE, COL_FLASH, COL_MEM, COL_STATUS, COL_PROGRESS, COL_DEL = range(7)


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

        # ---- 工具条
        tools = QHBoxLayout()
        tools.setSpacing(theme.GAP_SM)
        self.btn_add = PushButton(FIF.ADD, '添加')
        self.btn_del_pending = PushButton('删除未开始')
        self.chk_abort = CheckBox('失败即中止')
        self.chk_abort.setToolTip('不勾选：失败跳过继续下一个（旧行为）')
        self.btn_start = PrimaryPushButton(FIF.PLAY, '开始')
        self.btn_pause = PushButton(FIF.PAUSE, '暂停')
        self.btn_resume = PushButton(FIF.PLAY_SOLID, '继续')
        self.btn_stop = PushButton(FIF.CLOSE, '停止')
        self.btn_lock = PushButton('锁定')
        for w in (self.btn_add, self.btn_del_pending, self.chk_abort,
                  self.btn_start, self.btn_pause, self.btn_resume,
                  self.btn_stop, self.btn_lock):
            tools.addWidget(w)
        tools.addStretch(1)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(False)
        v.addLayout(tools)

        # ---- 任务表
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ['文件', '大小', 'Flash', '目标', '状态', '进度', ''])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
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
        self.table.setItem(row, COL_STATUS,
                           item(STATUS_TEXT.get(t.status, t.status)))

        flash_combo = QComboBox()
        flash_combo.addItems(FLASH_MAP.keys())
        flash_combo.setEnabled(editable)
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
        mem_combo.currentTextChanged.connect(
            lambda key, r=row: self._set_mem(r, key))
        self.table.setCellWidget(row, COL_MEM, mem_combo)
        for key, val in MEM_MAP.items():
            if val == t.mem_value:
                mem_combo.setCurrentText(key)
                break

        bar = QProgressBar()
        bar.setRange(0, 100)
        pct = int(t.transferred * 100 / t.total) if t.total else 0
        bar.setValue(pct)
        self.table.setCellWidget(row, COL_PROGRESS, bar)

        del_btn = QPushButton('删除')
        del_btn.setEnabled(editable)
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
        self._dark = dark
        theme.apply_theme(self, dark)
        self.conn.set_dark(dark)
        self.log_view.setStyleSheet(
            'QTextEdit{background:%s; color:%s; border:1px solid %s;'
            'border-radius:%dpx; font-family:"%s","Consolas"; font-size:12px;}'
            % (theme.C_CARD_D if dark else theme.C_CARD,
               theme.C_TEXT_D if dark else theme.C_TEXT,
               theme.C_GRAY_BG_D if dark else theme.C_GRAY_BG,
               theme.R_CARD, theme.FONT_FAMILY))
        theme.fix_fonts(self)

    def toggle_theme(self):
        self.apply_theme(not self._dark)

    def closeEvent(self, e):
        self.queue.cancel()
        self.link.close()
        super(TransferApp, self).closeEvent(e)
