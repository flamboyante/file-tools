# -*- coding: utf-8 -*-
"""serial_link 冒烟测试（无硬件，注入回环假串口）。

验证点：
1. open 成功 → opened 信号、state=OPEN
2. open 不存在的 COM → error 信号、state=FAULT（真实 pyserial 路径）
3. send 入队 → writer 整帧写出 → 假串口回环 → reader 收到 → rx 信号
4. 多帧发送顺序保持（队列 FIFO，字节不交错）
5. close 幂等、无僵尸线程（两个 QThread 都退出）、closed 信号

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_serial_link.py
"""
import os
import sys
import time
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtCore import QCoreApplication, QTimer
from Media.Media import MediaType

# 模拟 pyserial 的 read 超时行为：没数据时短暂阻塞（释放 GIL + 不空转）
FAKE_READ_TIMEOUT = 0.02


class FakeSerial(object):
    """pyserial 替身：write 的数据原样回灌到读缓冲（回环）。

    ⚠️ 忠实模拟两点，否则测出的全是假象：
    1. rxbuf 读写加锁 —— 真串口是 OS 缓冲，裸 bytearray 并发会丢字节
    2. read 无数据时阻塞 FAKE_READ_TIMEOUT —— 真串口 read(timeout=50ms)
       阻塞在 C 层释放 GIL；立即返回会让 reader 线程吃满 GIL
    """

    def __init__(self, *a, **kw):
        self.is_open = True
        self._rxbuf = bytearray()
        self._lock = threading.Lock()
        self._evt = threading.Event()
        self.written = []          # 记录每次 write 的完整帧（验原子性）

    def read(self, n):
        with self._lock:
            if not self._rxbuf:
                self._evt.clear()
        # 阻塞等待（模拟 timeout；write 时 set 唤醒）
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
            self._rxbuf.extend(data)   # 回环
            self._evt.set()
        return len(data)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False


class FakeMedia(object):
    """Media.SerialMedia 替身。"""

    def __init__(self):
        self.type = MediaType.SERIAL
        self.serial = FakeSerial()
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


def main():
    app = QCoreApplication(sys.argv)
    from uicmp.guicore.serial_link import SerialLink

    events = {'opened': 0, 'closed': 0, 'errors': [], 'rx': [], 'tx': []}

    # ---- 1. 打开不存在的 COM（真实 pyserial 路径，Windows 上必失败）
    bad = SerialLink()
    bad.error.connect(lambda m: events['errors'].append(m))
    ok = bad.open('COM_DELETED_XYZ')
    assert ok is False, '不存在的 COM 竟然打开成功'
    assert events['errors'], '失败时没有 error 信号'
    print('1. 打开失败路径 OK ->', events['errors'][0][:60])

    # ---- 2. 回环打开
    events['errors'].clear()
    link = SerialLink()
    link.opened.connect(lambda: events.__setitem__('opened', events['opened'] + 1))
    link.closed.connect(lambda: events.__setitem__('closed', events['closed'] + 1))
    link.error.connect(lambda m: events['errors'].append(m))
    link.rx.connect(lambda b: events['rx'].append(bytes(b)))
    link.tx_done.connect(lambda n: events['tx'].append(n))

    fake = FakeMedia()
    assert link.open('FAKE', media=fake) is True
    assert link.is_open
    assert events['opened'] == 1
    print('2. 打开成功 OK (state=%s)' % link.state)

    # ---- 3/4. 多帧发送 → 回环 → 字节流完整送达
    # rx 是**字节块**（流语义，一次可能含多帧），不是帧事件——组帧是
    # session 层的事。判据：拼起来的字节流 == 发出的字节流，且写入侧
    # 每帧单独 write（原子性，不交错）。
    frames = [bytes([0xEB, 0x90, i, i, i]) for i in range(1, 6)]
    stream = b''.join(frames)
    for f in frames:
        assert link.send(f) is True

    def check_roundtrip():
        got = b''.join(events['rx'])
        assert got == stream, '字节流不完整: got %d want %d' % (len(got), len(stream))
        assert fake.serial.written == frames, '写入侧帧被拆/交错: %r' % (fake.serial.written,)
        print('3. 回环 OK：字节流 %d 字节完整，写入侧 %d 帧各自原子写出'
              % (len(got), len(fake.serial.written)))

        # ---- 5. 关闭：幂等 + 线程退出 + closed 信号
        r, w = link._reader, link._writer
        link.close()
        link.close()                      # 幂等
        assert events['closed'] == 1, 'closed 信号次数 != 1'
        assert not r.isRunning(), '读线程未退出'
        assert not w.isRunning(), '写线程未退出'
        assert not link.is_open
        assert link.send(b'\x00') is False
        print('5. 关闭幂等 OK，读写线程均已退出')
        print('SMOKE OK')
        app.quit()

    # 真事件循环驱动（跨线程 queued 信号的可靠送达）
    QTimer.singleShot(500, check_roundtrip)
    app.exec_()


if __name__ == '__main__':
    main()
