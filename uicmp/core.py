# -*- coding: utf-8 -*-
"""三方案 UI 对比 —— 共享层：数据 + 设备 + 收发。

========================================================================
设计原则（保证 C / A / B 三份实现的对比是公平的）
========================================================================
1. 本模块是**唯一**的数据与通信来源。三份实现都 import 它，
   不允许任何一份自己重写收发逻辑 —— 否则测出来的是「通信实现差异」，
   而不是「界面实现差异」，整个对比就失去意义。

2. 本模块**不含任何渲染逻辑**：不创建 widget、不生成 QPixmap、不拼 HTML。
   判据：本文件里出现 QWidget / QPainter / QVBoxLayout / <div> 任何一个词，
   就说明边界划错了。

3. 数据来自 uicmp/case.json（三份共读同一份），不复用各自的 PRESETS。

------------------------------------------------------------------------
分层（自下而上）
------------------------------------------------------------------------
    WorkClass/CANCommandScheduler    零 Qt，数据模型 + 调度
    WorkClass/CanStreamWorkers       QThread，收发
    uicmp/core.py   ← 本文件         把上面两层组装成 UI 友好的门面
    三份 impl_*.py                    只负责渲染

关于 Qt 依赖：本模块用了 pyqtSignal。这不构成对任何一方的偏袒 ——
B 方案（QWebEngine）本身就跑在 QWidget 里，signal 照用，只是多一层
QWebChannel 桥接到 JS。
"""
import json
import os
import sys

from PyQt5.QtCore import QObject, pyqtSignal

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from WorkClass.CANCommandScheduler import deserialize_commands          # noqa: E402
from WorkClass.CanStreamWorkers import CanTxWorker, CanRecvWorker        # noqa: E402
from JiangCan_Tools.ECAN import ECAN, BaudRate, CAN_OBJ, Channel1, Channel2  # noqa: E402


# ------------------------------------------------------------------ 常量
CHAN_A = 'A'
CHAN_B = 'B'
CHANNELS = (CHAN_A, CHAN_B)

BAUD_LABEL = '500K'
TX_OK = 1                                   # ECAN transmit 成功返回码

DLL_REL = os.path.join('JiangCan_Tools', 'ECanVci64.dll')
DLL_FALLBACK = os.path.join('dist', 'Can_Frame_Deal', 'ECanVci64.dll')

CASE_PATH = os.path.join(_ROOT, 'uicmp', 'case.json')


class Mode(object):
    """设备模式。AUTO 会在真机不可用时自动回退到模拟。"""
    AUTO = 'auto'
    REAL = 'real'
    SIM = 'sim'


# ------------------------------------------------------------- 数据入口
def load_case(path=None):
    """读统一测试用例，返回 (cmds_a, cmds_b)。

    三份实现都调这一个函数 —— 这是「公平对比」的数据前提。
    返回的是独立的 CanCommand 对象，各实现可自由增删改，互不影响。
    """
    p = path or CASE_PATH
    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)
    cmds = deserialize_commands(data.get('commands', []))
    return ([c for c in cmds if c.channel == CHAN_A],
            [c for c in cmds if c.channel == CHAN_B])


def case_source():
    """返回 case.json 的来源说明（UI 可显示，证明三份读的是同一份）。"""
    try:
        with open(CASE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('source', '')
    except Exception:
        return ''


def to_can_obj(frame):
    """CanFrame -> ECAN 的 CAN_OBJ。

    三份共用，避免任何一份把 ExternFlag 写错（29 位 ID 必须置 1，
    写错的表现是「能发出去但帧在总线上非法」，不会报错）。
    """
    obj = CAN_OBJ()
    obj.ID = frame.id
    obj.DataLen = len(frame.data)
    for i, b in enumerate(frame.data):
        obj.data[i] = b & 0xFF
    obj.RemoteFlag = 0
    obj.ExternFlag = 1 if frame.id > 0x7FF else 0
    obj.SendType = 0
    return obj


def fmt_frame(frame):
    """统一的帧显示格式：'0x31801  00 5A 5A'。三份共用，保证文本一致。"""
    return '0x%X  %s' % (frame.id, ' '.join('%02X' % b for b in frame.data))


# --------------------------------------------------------------- 通道门面
class CanBus(QObject):
    """通道门面：开/关设备 + 单发 + 收发事件流。

    对 UI 只暴露三组信号，渲染方式各实现自己决定：
        txResult(channel, ok, tag, frame_idx, frame_total)
        rxFrame(channel, frame_id, data_list)
        busState(channel, opened, message)

    真机打不开时（没插设备 / DLL 缺失）在 AUTO 模式下自动回退到模拟，
    这样没有硬件也能把界面跑起来、出截图、验证数据流方向。
    模拟模式会真实模拟「A 发 → B 收」（假定两通道接同一总线）。
    """

    txResult = pyqtSignal(str, int, str, int, int)
    rxFrame = pyqtSignal(str, int, list)
    busState = pyqtSignal(str, bool, str)

    def __init__(self, mode=Mode.AUTO, parent=None):
        super(CanBus, self).__init__(parent)
        self._mode = mode
        self._device_opened = False
        self.simulating = False
        self._can = {}
        self._tx = {}
        self._rx = {}

    # -------------------------------------------------------- 通道开关
    def is_open(self, ch):
        return ch in self._tx

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

        # 回退到模拟
        self.simulating = True
        self._tx[ch] = None
        self._rx[ch] = None
        note = '已连接 · 模拟'
        if getattr(self, '_last_error', ''):
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
            if self._device_opened and ECAN.is_open:
                try:
                    ECAN.close()
                except Exception:
                    pass
                self._device_opened = False
        self.busState.emit(ch, False, '已断开')

    def shutdown(self):
        for ch in list(self._tx.keys()):
            self.close_channel(ch)

    # ------------------------------------------------------------ 发送
    def send_once(self, cmd):
        """单发一条指令的全部帧。最小集里「发送」只保留这一个入口。"""
        ch = cmd.channel
        if not self.is_open(ch):
            self.busState.emit(ch, False, '通道 %s 未打开' % ch)
            return False
        total = len(cmd.frames)
        for i, f in enumerate(cmd.frames):
            if self.simulating:
                self.txResult.emit(ch, TX_OK, cmd.name, i, total)
                self._sim_echo(ch, f)
            else:
                self._tx[ch].enqueue(to_can_obj(f), tag=cmd.name,
                                     frame_idx=i, frame_total=total)
        return True

    def _sim_echo(self, src_ch, frame):
        """模拟「另一通道收到」—— 前提是那一通道也开着（同一总线）。"""
        other = CHAN_B if src_ch == CHAN_A else CHAN_A
        if self.is_open(other):
            self.rxFrame.emit(other, frame.id, list(frame.data))

    # ------------------------------------------------------ 真机（内部）
    def _open_real(self, ch):
        try:
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

    def _on_tx_result(self, ch, ok, code, tag, idx, total):
        self.txResult.emit(ch, ok, tag, idx, total)

    def _on_rx_frame(self, ch, fid, data):
        self.rxFrame.emit(ch, fid, list(data))
