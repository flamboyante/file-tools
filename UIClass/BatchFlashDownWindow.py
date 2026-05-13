import os
from dataclasses import dataclass

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from Serial_thread import BatchFileTransfer_Work
from logging_config import log_print


TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_DONE = "done"
TASK_FAILED = "failed"
TASK_SKIPPED = "skipped"

STATUS_COLORS = {
    TASK_PENDING: QColor("#ffffff"),
    TASK_RUNNING: QColor("#fff4cc"),
    TASK_DONE: QColor("#edf1f5"),
    TASK_FAILED: QColor("#fde2e2"),
    TASK_SKIPPED: QColor("#f7f7f7"),
}

STATUS_TEXT = {
    TASK_PENDING: "待执行",
    TASK_RUNNING: "执行中",
    TASK_DONE: "已完成",
    TASK_FAILED: "失败",
    TASK_SKIPPED: "已跳过",
}


@dataclass
class BatchDownloadTask:
    file_path: str
    file_size: int
    flash_key: str
    flash_value: int
    mem_key: str
    mem_value: int
    status: str = TASK_PENDING
    progress: int = 0
    error: str = ""


def can_edit_task(task: BatchDownloadTask, globally_locked=False) -> bool:
    return task.status == TASK_PENDING and not globally_locked


def can_delete_task(task: BatchDownloadTask, globally_locked=False) -> bool:
    return task.status == TASK_PENDING and not globally_locked


def set_task_status(task: BatchDownloadTask, status: str, error="", progress=None):
    task.status = status
    task.error = error
    if progress is not None:
        task.progress = progress


class DropArea(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super(DropArea, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")

        layout = QVBoxLayout(self)
        title = QLabel("拖入多个文件，生成批量重构任务")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel("每一行选择 Flash 和部件，点击开始后按顺序连续下载")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addStretch(1)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                paths.append(path)
        if paths:
            self.files_dropped.emit(paths)


class BatchFlashDownWindow(QDialog):
    COL_FILE = 0
    COL_SIZE = 1
    COL_FLASH = 2
    COL_MEM = 3
    COL_STATUS = 4
    COL_PROGRESS = 5
    COL_ACTION = 6

    def __init__(self, parent=None):
        super(BatchFlashDownWindow, self).__init__(parent)
        self.mainWindow = None
        self.tasks = []
        self.running_tasks = []
        self.global_locked = False
        self.batch_worker = None

        self.mem_value_mapping = self._build_mem_mapping()
        self.flash_value_mapping = {
            "基带": 0xFB,
            "基带2": 0x9B,
            "SC": 0xFA,
        }

        self.setWindowTitle("批量版本重构")
        self.resize(1180, 720)
        self.setAcceptDrops(True)
        self._build_ui()
        self._apply_styles()
        self.refresh_table()

    def _build_mem_mapping(self):
        return {
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

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("添加文件")
        self.delete_button = QPushButton("删除未开始")
        self.lock_button = QPushButton("全局锁定")
        self.start_button = QPushButton("开始批量")
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")
        self.start_button.setObjectName("primaryButton")
        self.stop_button.setObjectName("dangerButton")
        for button in [self.add_button, self.delete_button, self.lock_button, self.start_button, self.pause_button, self.stop_button]:
            toolbar.addWidget(button)
        toolbar.addStretch(1)

        settings = QGridLayout()
        self.slice_check = QCheckBox("分片")
        self.slice_check.setChecked(True)
        self.frame_len_edit = QLineEdit("1000")
        self.frame_num_edit = QLineEdit("1024")
        self.interval_edit = QLineEdit("1000")
        settings.addWidget(QLabel("全局参数"), 0, 0)
        settings.addWidget(self.slice_check, 0, 1)
        settings.addWidget(QLabel("帧长"), 0, 2)
        settings.addWidget(self.frame_len_edit, 0, 3)
        settings.addWidget(QLabel("段帧数"), 0, 4)
        settings.addWidget(self.frame_num_edit, 0, 5)
        settings.addWidget(QLabel("任务间隔(ms)"), 0, 6)
        settings.addWidget(self.interval_edit, 0, 7)
        settings.setColumnStretch(8, 1)

        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self.add_files)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["文件", "大小", "Flash", "部件", "状态", "进度", "操作"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_FILE, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_MEM, QHeaderView.Stretch)
        self.table.setColumnWidth(self.COL_SIZE, 90)
        self.table.setColumnWidth(self.COL_FLASH, 120)
        self.table.setColumnWidth(self.COL_STATUS, 90)
        self.table.setColumnWidth(self.COL_PROGRESS, 150)
        self.table.setColumnWidth(self.COL_ACTION, 90)
        self.table.hide()

        self.total_progress = QProgressBar()
        self.total_progress.setRange(0, 100)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(130)

        root.addLayout(toolbar)
        root.addLayout(settings)
        root.addWidget(self.drop_area)
        root.addWidget(self.table, 1)
        root.addWidget(QLabel("总进度"))
        root.addWidget(self.total_progress)
        root.addWidget(self.log_edit)

        self.add_button.clicked.connect(self.choose_files)
        self.delete_button.clicked.connect(self.delete_pending_tasks)
        self.lock_button.clicked.connect(self.toggle_global_lock)
        self.start_button.clicked.connect(self.start_batch)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_batch)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog { background: #f6f8fb; color: #1f2937; }
            QLabel { color: #334155; }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cfd7e3;
                border-radius: 7px;
                padding: 7px 13px;
            }
            QPushButton:hover { background: #eef4ff; border-color: #8fb5ff; }
            QPushButton#primaryButton {
                background: #2563eb;
                color: #ffffff;
                border-color: #2563eb;
                font-weight: 600;
            }
            QPushButton#dangerButton:hover {
                background: #fff1f2;
                border-color: #fb7185;
                color: #be123c;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d8dee9;
                border-radius: 8px;
                gridline-color: #edf1f5;
                selection-background-color: #dbeafe;
            }
            QHeaderView::section {
                background: #f1f5f9;
                border: none;
                border-right: 1px solid #e2e8f0;
                padding: 7px;
                font-weight: 600;
            }
            QTextEdit, QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #cfd7e3;
                border-radius: 6px;
                padding: 4px;
            }
            QFrame#dropArea {
                background: #ffffff;
                border: 2px dashed #9bb7dc;
                border-radius: 10px;
                min-height: 190px;
            }
            QLabel#dropTitle {
                color: #1e40af;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#dropHint {
                color: #64748b;
                font-size: 13px;
            }
        """)

    def choose_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择批量重构文件", "", "All Files (*)")
        self.add_files(file_paths)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                paths.append(path)
        self.add_files(paths)

    def add_files(self, file_paths):
        default_flash_key = next(iter(self.flash_value_mapping))
        default_mem_key = next(iter(self.mem_value_mapping))
        for file_path in file_paths:
            if not os.path.isfile(file_path):
                continue
            task = BatchDownloadTask(
                file_path=file_path,
                file_size=os.path.getsize(file_path),
                flash_key=default_flash_key,
                flash_value=self.flash_value_mapping[default_flash_key],
                mem_key=default_mem_key,
                mem_value=self.mem_value_mapping[default_mem_key],
            )
            self.tasks.append(task)
            self.append_log(f"添加任务: {file_path}")
        self.refresh_table()

    def refresh_table(self):
        self.table.setVisible(bool(self.tasks))
        self.drop_area.setVisible(not self.tasks)
        self.table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            self._render_row(row, task)
        self._update_total_progress()

    def _render_row(self, row, task):
        editable = can_edit_task(task, self.global_locked)
        color = STATUS_COLORS.get(task.status, QColor("#ffffff"))
        status_text = STATUS_TEXT.get(task.status, task.status)

        file_item = QTableWidgetItem(os.path.basename(task.file_path))
        file_item.setToolTip(task.file_path)
        size_item = QTableWidgetItem(self._format_size(task.file_size))
        status_item = QTableWidgetItem(status_text)
        if task.error:
            status_item.setToolTip(task.error)
        for item in [file_item, size_item, status_item]:
            item.setBackground(QBrush(color))
        self.table.setItem(row, self.COL_FILE, file_item)
        self.table.setItem(row, self.COL_SIZE, size_item)
        self.table.setItem(row, self.COL_STATUS, status_item)

        flash_combo = QComboBox()
        flash_combo.addItems(self.flash_value_mapping.keys())
        flash_combo.setCurrentText(task.flash_key)
        flash_combo.setEnabled(editable)
        flash_combo.currentTextChanged.connect(lambda text, t=task: self._update_flash(t, text))
        self.table.setCellWidget(row, self.COL_FLASH, flash_combo)

        mem_combo = QComboBox()
        mem_combo.addItems(self.mem_value_mapping.keys())
        mem_combo.setCurrentText(task.mem_key)
        mem_combo.setEnabled(editable)
        mem_combo.currentTextChanged.connect(lambda text, t=task: self._update_mem(t, text))
        self.table.setCellWidget(row, self.COL_MEM, mem_combo)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(task.progress)
        self.table.setCellWidget(row, self.COL_PROGRESS, progress)

        delete_button = QPushButton("删除")
        delete_button.setEnabled(can_delete_task(task, self.global_locked))
        delete_button.clicked.connect(lambda checked=False, t=task: self.delete_task(t))
        self.table.setCellWidget(row, self.COL_ACTION, delete_button)

    def _update_flash(self, task, flash_key):
        if can_edit_task(task, self.global_locked):
            task.flash_key = flash_key
            task.flash_value = self.flash_value_mapping[flash_key]

    def _update_mem(self, task, mem_key):
        if can_edit_task(task, self.global_locked):
            task.mem_key = mem_key
            task.mem_value = self.mem_value_mapping[mem_key]

    def delete_task(self, task):
        if can_delete_task(task, self.global_locked):
            self.tasks.remove(task)
            self.refresh_table()

    def delete_pending_tasks(self):
        self.tasks = [task for task in self.tasks if not can_delete_task(task, self.global_locked)]
        self.refresh_table()

    def toggle_global_lock(self):
        self.global_locked = not self.global_locked
        self.lock_button.setText("解除锁定" if self.global_locked else "全局锁定")
        self.refresh_table()

    def start_batch(self):
        try:
            self._validate_before_start()
            self.global_locked = True
            self.lock_button.setText("解除锁定")
            self.running_tasks = [task for task in self.tasks if task.status == TASK_PENDING]
            self.batch_worker = BatchFileTransfer_Work(
                self.mainWindow.Serial_Worker,
                self.running_tasks,
                divide=self.slice_check.isChecked(),
                frame_len=int(self.frame_len_edit.text()),
                frame_num=int(self.frame_num_edit.text()),
                interval_ms=int(self.interval_edit.text()),
            )
            self.batch_worker.task_status_signal.connect(self.on_task_status)
            self.batch_worker.task_progress_signal.connect(self.on_task_progress)
            self.batch_worker.batch_complete_signal.connect(self.on_batch_complete)
            self.batch_worker.batch_failed_signal.connect(self.on_batch_failed)
            self.batch_worker.start()
            self.append_log("批量下载开始")
            self.refresh_table()
        except Exception as exc:
            QMessageBox.warning(self, "批量重构", str(exc))
            self.append_log(f"启动失败: {exc}")

    def _validate_before_start(self):
        if self.batch_worker is not None:
            raise ValueError("批量任务正在执行")
        if self.mainWindow is None or not self.mainWindow.Serial_Worker.status:
            raise ValueError("主通信未连接")
        if not any(task.status == TASK_PENDING for task in self.tasks):
            raise ValueError("没有可执行的 pending 任务")
        for task in self.tasks:
            if task.status == TASK_PENDING and not os.path.isfile(task.file_path):
                raise ValueError(f"文件不存在: {task.file_path}")

        for edit, name in [
            (self.frame_len_edit, "帧长"),
            (self.frame_num_edit, "段帧数"),
            (self.interval_edit, "任务间隔"),
        ]:
            try:
                value = int(edit.text())
            except ValueError:
                raise ValueError(f"{name}必须为正整数")
            if value <= 0:
                raise ValueError(f"{name}必须为正整数")

    def toggle_pause(self):
        if self.batch_worker is None:
            return
        if self.pause_button.text() == "暂停":
            self.batch_worker.send_pause()
            self.pause_button.setText("继续")
            self.append_log("当前任务暂停")
        else:
            self.batch_worker.send_resume()
            self.pause_button.setText("暂停")
            self.append_log("当前任务继续")

    def stop_batch(self):
        if self.batch_worker is not None:
            self.batch_worker.request_stop()
            self.append_log("已请求停止批量任务")

    def on_task_status(self, index, status, error):
        if index < len(self.running_tasks):
            progress = 100 if status == TASK_DONE else None
            set_task_status(self.running_tasks[index], status, error=error, progress=progress)
            if error:
                self.append_log(f"{os.path.basename(self.running_tasks[index].file_path)}: {error}")
        self.refresh_table()

    def on_task_progress(self, index, progress):
        if index < len(self.running_tasks):
            self.running_tasks[index].progress = self._calculate_progress(self.running_tasks[index], progress)
        self.refresh_table()

    def on_batch_complete(self):
        self.append_log("批量下载完成")
        self._cleanup_worker()
        self.refresh_table()

    def on_batch_failed(self, index, exc, trace):
        self.append_log(f"批量下载失败: {exc}")
        log_print(trace)
        self._cleanup_worker()
        self.refresh_table()

    def _cleanup_worker(self):
        if self.batch_worker is not None:
            try:
                if self.batch_worker.isRunning():
                    self.batch_worker.quit()
                    self.batch_worker.wait()
            except Exception:
                pass
        self.batch_worker = None
        self.running_tasks = []
        self.pause_button.setText("暂停")

    def closeEvent(self, event):
        if self.batch_worker is not None:
            self.batch_worker.request_stop()
        self._cleanup_worker()
        super(BatchFlashDownWindow, self).closeEvent(event)

    def append_log(self, text):
        self.log_edit.append(text)

    def _update_total_progress(self):
        if not self.tasks:
            self.total_progress.setValue(0)
            return
        total = sum(task.progress for task in self.tasks)
        self.total_progress.setValue(int(total / len(self.tasks)))

    def _calculate_progress(self, task, transferred):
        if task.file_size <= 0:
            return 0
        return max(0, min(100, int(transferred / task.file_size * 100)))

    def _format_size(self, size):
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"
