# -*- coding: utf-8 -*-
"""fake_device · 冒烟测试共用的 422 假设备应答器（无硬件回环）。

被 smoke_transfer_session / smoke_transfer_queue 引用。
帧布局判据与真机对齐（详见 mk_ack docstring）。

⚠️ 假串口必须忠实模拟 pyserial 两点，否则测出的是假象（踩过）：
1. rxbuf 加锁 —— 裸 bytearray 跨线程 extend/del 并发会丢字节
2. read 无数据时阻塞等待 —— 立即返回会让读线程吃满 GIL，
   queued 信号在 processEvents 轮询下假性失联
"""
import threading

from bmu_testkit.protocol.ycyk422 import checksum

FAKE_READ_TIMEOUT = 0.02     # 模拟 read timeout（秒）


class FakeSerialBase(object):
    """pyserial 替身：write 数据回灌读缓冲（回环），加锁 + 阻塞读。"""

    def __init__(self, *a, **kw):
        self.is_open = True
        self._rxbuf = bytearray()
        self._lock = threading.Lock()
        self._evt = threading.Event()
        self.written = []

    def read(self, n):
        with self._lock:
            if not self._rxbuf:
                self._evt.clear()
        self._evt.wait(FAKE_READ_TIMEOUT)
        with self._lock:
            out = bytes(self._rxbuf[:n])
            del self._rxbuf[:n]
        return out

    def inWaiting(self):
        with self._lock:
            return len(self._rxbuf)

    def write(self, data):
        data = bytes(data)
        with self._lock:
            self.written.append(data)
            self._rxbuf.extend(data)
            self._evt.set()
        return len(data)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False


def mk_ack(type_code, status=0):
    """构造 13 字节应答帧。

    布局（对照真样本 1A CF 01 87 C0 62 00 01 00 1F FE 35，心跳应答
    ircode=0x001F 落在 resp[8:10]，resp[9] 是其低字节）：
        1ACF | apid2 | seq2 | len-1=00 02 | 数据域3 | 校验2
        数据域3 = [ircode_hi=0x00, type_code, status]
        → resp[9]=type_code, resp[10]=status（与老代码 frame[9]/[10] 判据对齐）
    """
    p = bytearray(b'\x1A\xCF\x01\x87\xC0\x62\x00\x02')
    p += bytes([0x00, type_code, status])
    c = checksum(bytes(p[2:]))
    p += bytes([(c >> 8) & 0xFF, c & 0xFF])
    return bytes(p)


def classify(tx):
    """按组包特征识别指令类型。

    组包布局：id(2) apid(2) seq(2) [packet_len(2) 服务类型 功能码] ...
    → 功能码在 tx[9]，packet_len 在 tx[6:8]。
    """
    if len(tx) < 12:
        return None
    if tx[3] & 0x0F == 0x0F:                       # send_datas: apid 低 4 位 = F
        return 0x8A
    if tx[6:8] == b'\x00\x10' and tx[9] == 0x55:    # begin
        return 0x5A
    if tx[6:8] == b'\x00\x01' and tx[9] == 0xAA:    # finish
        return 0xBB
    return None                                     # refactor(00 03) 等：不应答


class DeviceSerial(FakeSerialBase):
    """回环假串口 + 协议应答器。

    mute=True 装哑（测超时）；force_status 覆盖应答状态（测异常）。
    """

    mute = False
    force_status = 0

    def write(self, data):
        data = bytes(data)
        with self._lock:
            self.written.append(data)
            t = classify(data)
            if t is not None and not self.mute:
                self._rxbuf.extend(mk_ack(t, self.force_status))
                self._evt.set()
        return len(data)


class DeviceMedia(object):
    """Media.SerialMedia 替身（供 SerialLink.open(media=...) 注入）。"""

    def __init__(self, serial=None):
        self.type = None
        self.serial = serial if serial is not None else DeviceSerial()
        self._open = True

    @property
    def is_open(self):
        return self._open

    def open(self):
        self._open = True

    def close(self):
        self._open = False

    def send(self, data):
        return self.serial.write(data)

    def recv(self, length):
        return self.serial.read(length)
