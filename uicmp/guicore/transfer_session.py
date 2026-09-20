# -*- coding: utf-8 -*-
"""transfer_session · 422 文件传输会话（单任务协议状态机）。

════════════════════════════════════════════════════════════════
流程（与旧 Serial_thread.FileTransfer_Work 逐步对齐，2026-09-20 核对）
════════════════════════════════════════════════════════════════
  1. send_begin(apid, file, flash, mem, divide, frame_len, frame_num)
       → 等应答 0x5A（resp[10]==0x00 通过 / 0xFF 参数异常）
       → sleep(1s)（旧代码的保守缓冲，保留）
  2. 数据循环：seg × frame，group_flag 首帧=1/中帧=0/末帧=2/单帧段=3
       每帧 → 等应答 0x8A → progress 信号
       暂停 = 门闸（pause Event），取消随时生效
  3. send_finish → 等应答 0xBB
  4. refactor_begin 发出即完（旧代码这一步不 等 应答）
       （重构结果查询 0xCA 属于独立的查询动作，不在传输流程内）

════════════════════════════════════════════════════════════════
与旧实现的本质区别
════════════════════════════════════════════════════════════════
- 旧：recv(13) 阻塞凑字节（12 字节心跳应答 → 永久死锁，老 bug #2+#3）
- 新：FrameAssembler 按帧头字段算帧长，任何长度都正确切帧；
      每步等待带 deadline，超时 = 可见的 TimeoutError 而不是无声卡死
- 旧：应答错误码 finally:return 吞掉（老 bug #1，已另行修复）
- 新：异常即 failed 信号，永不静默

组包复用 ycyk_422.Ycyk_422_Work（生产验证过），应答帧长计算复用
bmu_testkit.protocol.ycyk422——协议层零复制。
"""
import os
import queue
import threading
import time

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from ycyk_422 import Ycyk_422_Work
from uicmp.guicore.ycyk_framing import FrameAssembler

# 应答类型码（resp[9]）
ACK_BEGIN = 0x5A
ACK_DATA = 0x8A
ACK_FINISH = 0xBB
ACK_REFACTOR = 0xCA
# 应答状态（resp[10]）
ST_OK = 0x00
ST_ERR = 0xFF
ST_CRC = 0x11

_ACK_LABEL = {ACK_BEGIN: 'begin', ACK_DATA: 'data', ACK_FINISH: 'finish',
              ACK_REFACTOR: 'refactor'}

ACK_TIMEOUT = 5.0         # 每帧应答超时（秒）——超时是可见异常，不是卡死
BEGIN_SETTLE = 1.0        # begin 通过后的保守缓冲（对齐旧行为）
API_APID = 0x18           # 固定 apid（与旧代码一致；check_apid 按 flash 调整）


class TransferError(Exception):
    """协议层失败（应答异常/超时/链路断）。"""


class Cancelled(Exception):
    """用户取消，非错误。"""


class _TransferWorker(QThread):
    """驱动线程：顺序执行 begin→数据→finish→refactor，每步等应答。"""

    progress = pyqtSignal(int, int)      # transferred_bytes, total_bytes
    stage = pyqtSignal(str)              # 阶段/旁路日志
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, sess, file_path, flash, mem, divide, frame_len, frame_num):
        super(_TransferWorker, self).__init__()
        self._sess = sess
        self._args = (file_path, flash, mem, divide, frame_len, frame_num)
        self._pause_gate = threading.Event()
        self._pause_gate.set()           # set = 放行
        self._cancel_flag = False

    # ---- 控制（线程安全）
    def pause(self):
        self._pause_gate.clear()

    def resume(self):
        self._pause_gate.set()

    def cancel(self):
        self._cancel_flag = True
        self._pause_gate.set()           # 唤醒门闸里的等待者去检查取消

    def _gate(self):
        """暂停门闸 + 取消检查点（数据循环每帧调一次）。"""
        self._pause_gate.wait()
        if self._cancel_flag:
            raise Cancelled()

    # ---- 主流程
    def run(self):
        w = self._sess._new_worker()
        link = self._sess._link
        file_path, flash, mem, divide, frame_len, frame_num = self._args
        try:
            # ---- 1. begin
            self.stage.emit('发送 begin（flash=0x%02X mem=0x%02X）' % (flash, mem))
            pkt = w.send_begin(API_APID, file_path, flash, mem,
                               divide, frame_len, frame_num)
            self._send(link, pkt)
            self._wait_ack(ACK_BEGIN)
            time.sleep(BEGIN_SETTLE)

            # ---- 2. 数据
            total = os.path.getsize(file_path)
            transferred = 0
            self.stage.emit('开始传输数据（%d 字节）' % total)
            with open(file_path, 'rb') as f:
                for seg in range(w.segments):
                    frames = (w.segments_end_frames if seg == w.segments - 1
                              else w.frames)
                    for i in range(frames):
                        self._gate()
                        data = f.read(w.frame_size)
                        if not data:
                            break
                        if frames == 1:
                            flag = 3
                        elif i == 0:
                            flag = 1
                        elif i == frames - 1:
                            flag = 2
                        else:
                            flag = 0
                        self._send(link, w.send_datas(API_APID, seg, flag, data))
                        self._wait_ack(ACK_DATA)
                        transferred += len(data)
                        self.progress.emit(min(transferred, total), total)

            # ---- 3. finish
            self.stage.emit('发送 finish')
            self._send(link, w.send_finish(API_APID))
            self._wait_ack(ACK_FINISH)

            # ---- 4. refactor begin（发出即完，旧代码不等应答）
            self.stage.emit('发送重构启动')
            self._send(link, w.refactor_begin(API_APID, flash, mem))

            self.succeeded.emit()
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:
            if self._cancel_flag:
                self.cancelled.emit()
            else:
                self.failed.emit('%s: %s' % (type(e).__name__, e))

    # ---- 工具
    def _send(self, link, pkt):
        pkt = bytes(pkt)
        if not link.send(pkt):
            raise TransferError('链路未打开，%d 字节未发出' % len(pkt))

    def _wait_ack(self, expected):
        """等待指定类型应答。其他类型旁路（如 12 字节心跳应答）——
        正确切帧后它们只是过客，不再是死锁源。"""
        sess = self._sess
        deadline = time.time() + ACK_TIMEOUT
        label = _ACK_LABEL.get(expected, '0x%02X' % expected)
        while time.time() < deadline:
            if self._cancel_flag:
                raise Cancelled()
            try:
                frame = sess._ack_q.get(timeout=0.05)
            except queue.Empty:
                continue
            if len(frame) < 11:
                self.stage.emit('旁路短帧(%d 字节): %s' % (len(frame), frame.hex(' ')))
                continue
            type_code, status = frame[9], frame[10]
            if type_code != expected:
                self.stage.emit('旁路应答 type=0x%02X status=0x%02X（等 %s）'
                                % (type_code, status, label))
                continue
            if status == ST_OK:
                return frame
            if status == ST_ERR:
                raise TransferError('%s 应答异常(0xFF)' % label)
            if status == ST_CRC:
                raise TransferError('%s 应答 CRC 重构异常(0x11)' % label)
            raise TransferError('%s 应答未知状态 0x%02X' % (label, status))
        raise TransferError('等待 %s 应答超时（%.1fs）' % (label, ACK_TIMEOUT))


class TransferSession(QObject):
    """单任务传输会话。一次 start() 一个任务；批量由上层 TaskQueue 编排。

    用法：
        sess = TransferSession(link)          # link: SerialLink（422 共享链路）
        sess.progress.connect(...)
        sess.start(file, flash, mem, divide, frame_len, frame_num)
        sess.pause() / resume() / cancel()
    """

    progress = pyqtSignal(int, int)
    stage = pyqtSignal(str)
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, link, parent=None):
        super(TransferSession, self).__init__(parent)
        self._link = link
        self._link.rx.connect(self._on_rx)
        self._worker = None            # 当前 _TransferWorker
        self._asm = FrameAssembler()
        self._ack_q = queue.Queue()

    # ------------------------------------------------------------ 状态
    @property
    def is_running(self):
        return self._worker is not None and self._worker.isRunning()

    def _new_worker(self):
        """每任务新建协议构造器（计数清零，与旧 FlashDownWindow 行为一致）。"""
        return Ycyk_422_Work(id=0xEB90)

    # ------------------------------------------------------------ 收
    def _on_rx(self, data):
        for frame in self._asm.feed(bytes(data)):
            self._ack_q.put(frame)

    # ------------------------------------------------------------ 开工
    def start(self, file_path, flash, mem, divide, frame_len, frame_num):
        if self.is_running:
            self.failed.emit('已有传输在进行')
            return False
        if not os.path.isfile(file_path):
            self.failed.emit('文件不存在: %s' % file_path)
            return False
        self._worker = _TransferWorker(self, file_path, flash, mem,
                                       divide, frame_len, frame_num)
        # 转发信号（QThread 的信号 → session 的信号）
        self._worker.progress.connect(self.progress)
        self._worker.stage.connect(self.stage)
        self._worker.succeeded.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()
        return True

    # ------------------------------------------------------------ 控制
    def pause(self):
        if self._worker:
            self._worker.pause()

    def resume(self):
        if self._worker:
            self._worker.resume()

    def cancel(self):
        if self._worker:
            self._worker.cancel()

    # ------------------------------------------------------------ 收尾
    def _on_done(self):
        self._worker = None
        self.succeeded.emit()

    def _on_failed(self, msg):
        self._worker = None
        self.failed.emit(msg)

    def _on_cancelled(self):
        self._worker = None
        self.cancelled.emit()
