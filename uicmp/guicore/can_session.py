# -*- coding: utf-8 -*-
"""can_session · CAN 会话门面：设备 + 收发线程 + 定时调度。

合三处生产实现而成（2026-09-21 迁移，语义保持）：
- 设备层/模拟回退：`uicmp/core.py` 的 CanBus（A/B 原型共用层，真机验证过）
- 收发线程：`WorkClass/CanStreamWorkers.py`（CanTxWorker / CanRecvWorker）
- 调度器与命令模型：`WorkClass/CANCommandScheduler.py` → 已迁到 `can_commands.py`

对外只暴露信号与命令操作，**不含任何控件**（页面只管渲染）：
    txResult(channel, ok, tag, frame_idx, frame_total)
    rxFrame(channel, frame_id, data_list)
    busState(channel, opened, message)
    commandsChanged()          命令增删改/启停后（页面刷新列表）
    runStateChanged(bool)      定时发送开/关（页面切锁定）
    commandFinished(cmd)       某条指令次数用尽自动停（页面刷新那一条）

三项改进（相对旧实现）：
1. `ECAN` 延迟导入且失败降级到模拟——没有 dll / 没插设备也能起页面、出图、测数据流
2. 定时调度与单发走**同一条投递路径** `_dispatch()`，不会一处改了另一处忘
3. 统计（tx/rx/err）收进会话层，页面只读数字
"""
import os
import threading
from queue import Queue, Empty

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal

from uicmp.guicore.can_commands import (CanCommand, CANCommandScheduler,
                                        default_commands, serialize_commands,
                                        deserialize_commands)

CHAN_A = 'A'
CHAN_B = 'B'
CHANNELS = (CHAN_A, CHAN_B)

TX_OK = 1                    # ECAN transmit 成功返回码
TICK_MS = 40                 # 调度节拍（旧版同值）

DLL_REL = os.path.join('JiangCan_Tools', 'ECanVci64.dll')
DLL_FALLBACK = os.path.join('dist', 'Can_Frame_Deal', 'ECanVci64.dll')


class Mode(object):
    AUTO = 'auto'    # 真机优先，失败回退模拟
    REAL = 'real'    # 只要真机，打开失败即报错
    SIM = 'sim'      # 强制模拟


# ---------------------------------------------------------------- 收发线程
class _TxItem(object):
    __slots__ = ("obj", "tag", "frame_idx", "frame_total")

    def __init__(self, obj, tag, frame_idx, frame_total):
        self.obj = obj
        self.tag = tag
        self.frame_idx = frame_idx
        self.frame_total = frame_total


class CanTxWorker(QThread):
    """发送线程：逐帧 transmit，结果把来源（tag/序号）一并回传。"""

    tx_result = pyqtSignal(str, int, int, object, int, int)
    # (channel, ok(1/0), err_code, tag, frame_idx, frame_total)

    def __init__(self, can_dev, channel, parent=None):
        super(CanTxWorker, self).__init__(parent)
        self._can = can_dev
        self._channel = channel
        self._q = Queue(maxsize=2000)
        self._stop = threading.Event()

    def enqueue(self, can_obj, tag="", frame_idx=0, frame_total=1):
        try:
            self._q.put_nowait(_TxItem(can_obj, tag, frame_idx, frame_total))
            return True
        except Exception:
            return False

    def shutdown(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.05)
            except Empty:
                continue
            except Exception:
                break
            try:
                ret = self._can.transmit(item.obj)
                ok = 1 if ret == TX_OK else 0
            except Exception:
                ret, ok = -1, 0
            self.tx_result.emit(self._channel, ok, ret,
                                item.tag, item.frame_idx, item.frame_total)
        self._q = None


class CanRecvWorker(QThread):
    """接收线程：每收到一帧发一个带通道标识的原始信号。"""

    rx_frame = pyqtSignal(str, int, list)   # (channel, id, data)

    def __init__(self, can_dev, channel, parent=None):
        super(CanRecvWorker, self).__init__(parent)
        self._can = can_dev
        self._channel = channel
        self._stop = threading.Event()

    def shutdown(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                length, recv_arr, ret = self._can.receive(1)
            except Exception:
                break
            if length > 0 and ret == 1 and recv_arr:
                f = recv_arr[0]
                if f.RemoteFlag == 0:
                    data = [f.data[i] for i in range(f.DataLen)]
                    self.rx_frame.emit(self._channel, f.ID, data)
        self._stop.clear()


# ---------------------------------------------------------------- 会话门面
class CanSession(QObject):
    """CAN 会话：A/B 双通道设备 + 命令表 + 定时调度。

    页面只用这些入口，不直接碰 ECAN / QThread / 调度器。
    """

    txResult = pyqtSignal(str, int, str, int, int)
    rxFrame = pyqtSignal(str, int, list)
    busState = pyqtSignal(str, bool, str)
    commandsChanged = pyqtSignal()
    runStateChanged = pyqtSignal(bool)
    commandFinished = pyqtSignal(object)

    def __init__(self, mode=Mode.AUTO, parent=None):
        super(CanSession, self).__init__(parent)
        self._mode = mode
        self.simulating = False
        self._device_opened = False
        self._can = {}
        self._tx = {}
        self._rx = {}
        self._last_error = ''

        # 命令表（A/B 各自一份）
        self._cmds = {CHAN_A: default_commands(CHAN_A),
                      CHAN_B: default_commands(CHAN_B)}
        self._stats = {ch: {'tx': 0, 'rx': 0, 'err': 0} for ch in CHANNELS}
        self._running = False

        self.sched = CANCommandScheduler()
        self.sched.set_callback(self._dispatch)
        self.sched.set_commands(self.all_commands())

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------ 通道
    def is_open(self, ch):
        return ch in self._tx

    @property
    def any_open(self):
        return bool(self._tx)

    def open_channel(self, ch):
        if self.is_open(ch):
            return True

        if self._mode in (Mode.AUTO, Mode.REAL):
            ok, msg = self._open_real(ch)
            if ok:
                self.busState.emit(ch, True, '已连接 · 真机')
                return True
            if self._mode == Mode.REAL:
                self.busState.emit(ch, False, msg or '设备打开失败')
                return False
            self._last_error = msg
        else:
            self._last_error = ''

        # 回退模拟（无硬件/无 dll 也能跑通整条数据流）
        self.simulating = True
        self._tx[ch] = None
        self._rx[ch] = None
        note = '已连接 · 模拟'
        if self._last_error:
            note += '（%s）' % self._last_error
        self.busState.emit(ch, True, note)
        return True

    def close_channel(self, ch):
        for w in (self._tx.get(ch), self._rx.get(ch)):
            if w is not None:
                try:
                    w.shutdown()
                    w.quit()
                    w.wait(1200)
                except Exception:
                    pass
        self._tx.pop(ch, None)
        self._rx.pop(ch, None)
        self._can.pop(ch, None)

        if not self._tx:
            self.simulating = False
            if self._device_opened:
                self._close_device()
        self.busState.emit(ch, False, '已断开')

    def shutdown(self):
        self.stop_sending()
        for ch in list(self._tx.keys()):
            self.close_channel(ch)

    def _close_device(self):
        try:
            from JiangCan_Tools.ECAN import ECAN
            if getattr(ECAN, 'is_open', False):
                ECAN.close()
        except Exception:
            pass
        self._device_opened = False

    def _open_real(self, ch):
        try:
            try:
                from JiangCan_Tools.ECAN import ECAN, BaudRate, CAN_OBJ, Channel1, Channel2
            except Exception as e:
                return False, 'ECAN 模块不可用：%s' % e

            if not self._device_opened:
                dll = os.path.join(os.getcwd(), DLL_REL)
                if not os.path.exists(dll):
                    dll = os.path.join(os.getcwd(), DLL_FALLBACK)
                if not os.path.exists(dll):
                    return False, '找不到 ECanVci64.dll'
                ECAN.open(0, 0, dll)
                self._device_opened = True

            if ECAN.is_open is False:
                return False, '设备未打开（USBCAN 是否插好）'

            dev = ECAN(Channel1 if ch == CHAN_A else Channel2)
            if not dev.config(BaudRate.BAUD_500K):
                return False, 'config 失败'
            if not dev.start():
                return False, 'start 失败'

            tx = CanTxWorker(dev, ch, None)
            rx = CanRecvWorker(dev, ch, None)
            tx.tx_result.connect(self._on_tx_result)
            rx.rx_frame.connect(self._on_rx_frame)
            tx.start()
            rx.start()

            self._can[ch] = dev
            self._tx[ch] = tx
            self._rx[ch] = rx
            return True, ''
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------ 命令表
    def commands(self, ch):
        return self._cmds[ch]

    def all_commands(self):
        return self._cmds[CHAN_A] + self._cmds[CHAN_B]

    def load_presets(self):
        """恢复出厂预设（两个通道）。"""
        self._cmds = {CHAN_A: default_commands(CHAN_A),
                      CHAN_B: default_commands(CHAN_B)}
        self._resync_scheduler()
        self.commandsChanged.emit()

    def add_command(self, ch, cmd=None):
        cmd = cmd or CanCommand(name='新指令', channel=ch, interval_ms=500,
                                count=-1, enabled=False, frames=[])
        cmd.channel = ch
        self._cmds[ch].append(cmd)
        self.sched.add(cmd)
        self.commandsChanged.emit()
        return cmd

    def remove_command(self, ch, cmd):
        if cmd in self._cmds[ch]:
            self._cmds[ch].remove(cmd)
            self.sched.remove(cmd)
            self.commandsChanged.emit()

    def move_command(self, ch, cmd, delta):
        lst = self._cmds[ch]
        if cmd not in lst:
            return
        i = lst.index(cmd)
        j = max(0, min(len(lst) - 1, i + delta))
        if i != j:
            lst.insert(j, lst.pop(i))
            self.commandsChanged.emit()

    def set_enabled(self, cmd, on):
        cmd.enabled = bool(on)
        self.commandsChanged.emit()

    def replace(self, ch, cmds):
        """整表替换（导入配置用）。"""
        for c in cmds:
            c.channel = ch
        self._cmds[ch] = list(cmds)
        self._resync_scheduler()
        self.commandsChanged.emit()

    def serialize(self):
        return {'A': serialize_commands(self._cmds[CHAN_A]),
                'B': serialize_commands(self._cmds[CHAN_B])}

    def deserialize(self, data):
        self._cmds[CHAN_A] = deserialize_commands(data.get('A', []))
        self._cmds[CHAN_B] = deserialize_commands(data.get('B', []))
        self._resync_scheduler()
        self.commandsChanged.emit()

    def _resync_scheduler(self):
        self.sched.set_commands(self.all_commands())

    # ------------------------------------------------------------ 运行
    @property
    def is_running(self):
        return self._running

    def active_count(self):
        return self.sched.count_active()

    def start_sending(self):
        """返回 (ok, message)——页面据此提示。"""
        if self._running:
            return True, ''
        if not self.any_open:
            return False, '请先打开至少一个通道'
        if self.active_count() == 0:
            return False, '没有启用任何指令（打开某条指令的开关）'
        self._running = True
        self.sched.set_commands(self.all_commands())
        self.sched.reset_runtime()
        self._timer.start()
        self.runStateChanged.emit(True)
        return True, ''

    def stop_sending(self):
        if self._timer.isActive():
            self._timer.stop()
        self.sched.finish_silently()
        if self._running:
            self._running = False
            self.runStateChanged.emit(False)

    def send_once(self, cmd):
        """立即单发（不受运行锁限制）。"""
        if not self.is_open(cmd.channel):
            self.busState.emit(cmd.channel, False, '通道 %s 未打开' % cmd.channel)
            return False
        self._dispatch(cmd)
        return True

    def remaining_of(self, cmd):
        return self.sched.remaining_of(cmd)

    def stats(self, ch):
        return dict(self._stats[ch])

    # ------------------------------------------------------------ 内部
    def _tick(self):
        self.sched.tick()
        for cmd in self.sched.take_just_finished():
            self.commandFinished.emit(cmd)

    def _dispatch(self, cmd):
        """唯一投递路径：定时到期与立即单发都走这里。"""
        ch = cmd.channel
        if not self.is_open(ch):
            return
        total = len(cmd.frames)
        for i, f in enumerate(cmd.frames):
            if self.simulating:
                # 模拟分支也要计数（否则 SIM 下统计恒为 0——拼装时踩过）
                self._stats[ch]['tx'] += 1
                self.txResult.emit(ch, TX_OK, cmd.name, i, total)
                self._sim_echo(ch, f)
            else:
                worker = self._tx.get(ch)
                if worker is None:
                    return
                worker.enqueue(self._to_can_obj(f), tag=cmd.name,
                               frame_idx=i, frame_total=total)

    def _sim_echo(self, src_ch, frame):
        """模拟「另一通道收到」——前提是那一通道也开着（同一总线）。"""
        other = CHAN_B if src_ch == CHAN_A else CHAN_A
        if self.is_open(other):
            self._stats[other]['rx'] += 1
            self.rxFrame.emit(other, frame.id, list(frame.data))

    @staticmethod
    def _to_can_obj(frame):
        from JiangCan_Tools.ECAN import CAN_OBJ
        obj = CAN_OBJ()
        obj.ID = frame.id
        obj.DataLen = len(frame.data)
        for i, b in enumerate(frame.data):
            obj.data[i] = b & 0xFF
        obj.RemoteFlag = 0
        obj.ExternFlag = 1 if frame.id > 0x7FF else 0
        obj.SendType = 0
        return obj

    def _on_tx_result(self, ch, ok, code, tag, idx, total):
        if ok:
            self._stats[ch]['tx'] += 1
        else:
            self._stats[ch]['err'] += 1
        self.txResult.emit(ch, ok, tag, idx, total)

    def _on_rx_frame(self, ch, fid, data):
        self._stats[ch]['rx'] += 1
        self.rxFrame.emit(ch, fid, list(data))
