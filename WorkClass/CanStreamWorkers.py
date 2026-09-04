"""新 CAN 窗口的收发工作线程。

- CanTxWorker: 一条队列线程，逐帧 transmit 并把"返回码是否成功"实时回传 UI。
  入队对象可携带来源 tag（指令名）与帧序号，发送结果 signal 原样带回，
  供 UI 把结果映射到具体指令卡片。
- CanRecvWorker: 单通道接收线程，每帧一个带通道/ID/数据的原始 signal
  （不复用旧的字符串聚合 JCANThread，保证 A/B 通道标识可区分）。
"""
import threading
from queue import Queue, Empty

from PyQt5.QtCore import QThread, pyqtSignal

STATUS_OK = 1  # ECAN 底层成功返回码


class _TxItem(object):
    __slots__ = ("obj", "tag", "frame_idx", "frame_total")

    def __init__(self, obj, tag, frame_idx, frame_total):
        self.obj = obj
        self.tag = tag
        self.frame_idx = frame_idx
        self.frame_total = frame_total


class CanTxWorker(QThread):
    """发送线程：enqueue_frame(obj, tag, idx, total) -> 逐帧发送，结果带回来源。"""

    tx_result = pyqtSignal(str, int, int, object, int, int)
    # (channel, ok(1/0), err_code, tag, frame_idx, frame_total)

    def __init__(self, can_dev, channel, parent=None):
        super().__init__(parent)
        self._can = can_dev
        self._channel = channel
        self._q = Queue(maxsize=2000)
        self._stop = threading.Event()

    def enqueue_frame(self, can_obj, tag="", frame_idx=0, frame_total=1):
        try:
            self._q.put_nowait(_TxItem(can_obj, tag, frame_idx, frame_total))
            return True
        except Exception:
            return False
    def enqueue(self, can_obj, tag="", frame_idx=0, frame_total=1):
        return self.enqueue_frame(can_obj, tag, frame_idx, frame_total)

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
                ok = 1 if ret == STATUS_OK else 0
            except Exception:
                ret = -1
                ok = 0
            self.tx_result.emit(self._channel, ok, ret,
                                item.tag, item.frame_idx, item.frame_total)
        self._q = None


class CanRecvWorker(QThread):
    """单通道接收线程：每收到一帧发一帧原始数据（带通道）。"""

    rx_frame = pyqtSignal(str, int, list)   # (channel, id, data)

    def __init__(self, can_dev, channel, parent=None):
        super().__init__(parent)
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
