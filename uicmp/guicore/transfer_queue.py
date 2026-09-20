# -*- coding: utf-8 -*-
"""transfer_queue · 批量传输调度（顺序跑 N 个任务）。

设计（与旧 BatchFlashDownWindow 对齐 + 小K 拍板的策略开关）：
- 任务顺序执行，同一时刻只跑一个（共享 422 链路）
- 失败策略：SKIP（默认，失败跳过继续下一个——旧行为）/ ABORT（失败即停）
- 取消：当前任务取消 + 剩余全部标 SKIPPED
- 每个任务新建 TransferSession（共享 link，会话内部自建协议构造器）

任务模型对齐旧 BatchDownloadTask：PENDING/RUNNING/DONE/FAILED/SKIPPED。
「全局锁定」（禁止编辑待执行任务）是 UI 概念，在页面层，不进调度器。
"""
from dataclasses import dataclass, field

from PyQt5.QtCore import QObject, pyqtSignal

from uicmp.guicore.transfer_session import TransferSession

# 任务状态
T_PENDING = 'pending'
T_RUNNING = 'running'
T_DONE = 'done'
T_FAILED = 'failed'
T_SKIPPED = 'skipped'

# 失败策略
POLICY_SKIP = 'skip'
POLICY_ABORT = 'abort'


@dataclass
class TransferTask(object):
    file_path: str
    flash_value: int
    mem_value: int
    divide: int = 0
    frame_len: int = 1024
    frame_num: int = 1
    status: str = T_PENDING
    transferred: int = 0
    total: int = 0
    error: str = ''


class TransferQueue(QObject):
    """批量调度器。所有信号带任务下标（UI 按 index 刷新行）。"""

    task_changed = pyqtSignal(int)
    queue_finished = pyqtSignal(str)      # 汇总描述（成功 X / 失败 Y / 跳过 Z）
    queue_cancelled = pyqtSignal()

    def __init__(self, link, parent=None):
        super(TransferQueue, self).__init__(parent)
        self._link = link
        self._tasks = []
        self._idx = -1                    # 当前运行的任务下标
        self._sess = None
        self._policy = POLICY_SKIP
        self._cancelling = False

    # ------------------------------------------------------------ 状态
    @property
    def tasks(self):
        return self._tasks

    @property
    def is_running(self):
        return self._sess is not None

    @property
    def current_index(self):
        return self._idx

    # ------------------------------------------------------------ 开工
    def start(self, tasks, policy=POLICY_SKIP):
        """tasks: TransferTask 列表（只跑 status==PENDING 的）。"""
        if self.is_running:
            return False
        self._tasks = list(tasks)
        self._policy = policy
        self._cancelling = False
        self._run_next()
        return True

    def _run_next(self):
        # 清理上一个会话
        if self._sess is not None:
            self._sess.deleteLater()
            self._sess = None
            self._idx = -1
        # 找下一个待执行任务
        nxt = next((i for i, t in enumerate(self._tasks)
                    if t.status == T_PENDING), None)
        if nxt is None or self._cancelling:
            self._finish()
            return
        self._idx = nxt
        task = self._tasks[nxt]
        task.status = T_RUNNING
        task.error = ''
        self.task_changed.emit(nxt)

        sess = TransferSession(link=self._link, parent=self)
        self._sess = sess
        sess.progress.connect(lambda tr, tot, i=nxt: self._on_progress(i, tr, tot))
        sess.stage.connect(lambda m, i=nxt: None)     # 预留：队列级日志
        sess.succeeded.connect(lambda i=nxt: self._on_done(i))
        sess.failed.connect(lambda m, i=nxt: self._on_failed(i, m))
        sess.cancelled.connect(lambda i=nxt: self._on_cancelled(i))
        sess.start(task.file_path, task.flash_value, task.mem_value,
                   task.divide, task.frame_len, task.frame_num)

    # ------------------------------------------------------------ 会话回调
    def _on_progress(self, idx, transferred, total):
        t = self._tasks[idx]
        t.transferred = transferred
        t.total = total
        self.task_changed.emit(idx)

    def _on_done(self, idx):
        self._tasks[idx].status = T_DONE
        self.task_changed.emit(idx)
        self._run_next()

    def _on_failed(self, idx, msg):
        self._tasks[idx].status = T_FAILED
        self._tasks[idx].error = msg
        self.task_changed.emit(idx)
        if self._policy == POLICY_ABORT:
            self._cancelling = True
            for t in self._tasks:
                if t.status == T_PENDING:
                    t.status = T_SKIPPED
            self.task_changed.emit(-1)                # 全表刷新信号
            self._finish()
        else:
            self._run_next()

    def _on_cancelled(self, idx):
        self._tasks[idx].status = T_FAILED
        self._tasks[idx].error = '已取消'
        for t in self._tasks:
            if t.status in (T_PENDING, T_RUNNING):
                t.status = T_SKIPPED
        self.task_changed.emit(-1)
        self._cancelling = True
        self.queue_cancelled.emit()
        self._finish()

    def _finish(self):
        ok = sum(1 for t in self._tasks if t.status == T_DONE)
        bad = sum(1 for t in self._tasks if t.status == T_FAILED)
        skip = sum(1 for t in self._tasks if t.status == T_SKIPPED)
        self._sess = None
        self._idx = -1
        self.queue_finished.emit('完成 %d / 失败 %d / 跳过 %d' % (ok, bad, skip))

    # ------------------------------------------------------------ 控制
    def pause(self):
        if self._sess:
            self._sess.pause()

    def resume(self):
        if self._sess:
            self._sess.resume()

    def cancel(self):
        """取消队列：当前任务取消（会话层收尾），剩余由 _on_cancelled 标跳过。"""
        if self._sess:
            self._cancelling = True
            self._sess.cancel()
