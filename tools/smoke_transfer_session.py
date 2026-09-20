# -*- coding: utf-8 -*-
"""transfer_session 冒烟测试（无硬件：假链路 + 假设备应答器）。

场景：
A. 全流程成功：begin(0x5A) → 数据帧×N(0x8A) → finish(0xBB) → refactor
   假设备按协议类型码回 13 字节应答帧（checksum 用 bmu_testkit 计算）
B. 错类型应答旁路：等 begin 时先到 0x8A → 记 stage 旁路，继续等到 0x5A
C. 应答异常：数据应答 status=0xFF → failed 信号
D. 应答超时：设备装哑 → ACK_TIMEOUT 后 failed（不死锁！）
E. 传输中取消：进度 ≥5 帧后 cancel → cancelled 信号，线程退出

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_transfer_session.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication

from bmu_testkit.protocol.ycyk422 import checksum
from uicmp.guicore.serial_link import SerialLink
from uicmp.guicore.transfer_session import TransferSession

# 复用回环假串口的锁/阻塞语义
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'smoke_serial_link.py'), encoding='utf-8').read()
_ns = {'__file__': os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'smoke_serial_link.py')}
exec(_src.split('def main()')[0], _ns)
FakeSerial = _ns['FakeSerial']


# ---------------------------------------------------------- 假设备应答器
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


class DeviceSerial(FakeSerial):
    """回环假串口 + 协议应答器。mute=True 装哑（测超时）。"""

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
    def __init__(self, serial):
        self.type = None
        self.serial = serial
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


def make_session():
    link = SerialLink()
    dev = DeviceSerial()
    assert link.open('FAKE', media=DeviceMedia(dev)) is True
    sess = TransferSession(link=link)
    return link, dev, sess


def main():
    app = QApplication(sys.argv)
    assert QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc') != -1

    # 2500 字节测试文件（frame_size=1024 → 3 帧）
    tmpdir = tempfile.mkdtemp()
    payload = bytes(range(256)) * 10
    fpath = os.path.join(tmpdir, 'fw.bin')
    with open(fpath, 'wb') as f:
        f.write(payload)

    def watch(sess, box):
        sess.progress.connect(lambda a, b: box['progress'].append(a))
        sess.stage.connect(box['stages'].append)
        sess.succeeded.connect(lambda: box.__setitem__('done', True))
        sess.failed.connect(box['failed'].append)
        sess.cancelled.connect(lambda: box.__setitem__('cancelled', True))

    def spin_until(app, cond, timeout=10.0):
        """真事件循环驱动（跨线程 queued 信号的可靠送达）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if cond():
                return True
            app.processEvents()
            time.sleep(0.01)
        return False

    # ================= 场景 B+A：先错类型旁路，再全流程成功 ================
    link, dev, sess = make_session()
    box = {'progress': [], 'stages': [], 'failed': [], 'done': False,
           'cancelled': False}
    watch(sess, box)
    assert sess.start(fpath, flash=0x02, mem=0x12, divide=0,
                      frame_len=1024, frame_num=1) is True
    # 设备先回一个错误类型的应答（等 begin 时到了 data ack）
    time.sleep(0.3)
    link._media.serial._rxbuf.extend(mk_ack(0x8A))
    link._media.serial._evt.set()
    assert spin_until(app, lambda: box['done']), '全流程未完成: %r' % box['failed']
    assert box['failed'] == []
    assert box['progress'][-1] == len(payload), '进度未到满: %r' % box['progress'][-1]
    assert any('旁路' in s for s in box['stages']), '错类型应答未被旁路记录'
    print('A/B. 全流程成功 %d 字节 + 错类型旁路 OK' % len(payload))
    assert sess.is_running is False
    link.close()

    # ================= 场景 C：数据应答 status=0xFF → failed ================
    link, dev, sess = make_session()
    dev.force_status = 0xFF
    box = {'progress': [], 'stages': [], 'failed': [], 'done': False,
           'cancelled': False}
    watch(sess, box)
    assert sess.start(fpath, flash=0x02, mem=0x12, divide=0,
                      frame_len=1024, frame_num=1) is True
    assert spin_until(app, lambda: bool(box['failed']) or box['done']), '未收到 failed'
    assert box['failed'] and '0xFF' in box['failed'][0], '失败原因不对: %r' % box['failed']
    assert not box['done']
    print('C. 应答异常 → failed OK (%s)' % box['failed'][0])
    link.close()

    # ================= 场景 D：设备装哑 → 超时 failed（不死锁） ================
    import uicmp.guicore.transfer_session as ts_mod
    old_to = ts_mod.ACK_TIMEOUT
    ts_mod.ACK_TIMEOUT = 0.4                       # 缩短冒烟耗时
    link, dev, sess = make_session()
    dev.mute = True
    box = {'progress': [], 'stages': [], 'failed': [], 'done': False,
           'cancelled': False}
    watch(sess, box)
    assert sess.start(fpath, flash=0x02, mem=0x12, divide=0,
                      frame_len=1024, frame_num=1) is True
    assert spin_until(app, lambda: bool(box['failed']), timeout=8.0), '超时未触发 failed'
    assert '超时' in box['failed'][0], '应是超时错误: %r' % box['failed']
    ts_mod.ACK_TIMEOUT = old_to
    print('D. 应答超时 → failed OK（%.1fs 收尾，无死锁）' % 0.4)
    link.close()

    # ================= 场景 E：传输中取消 ================
    big = os.path.join(tmpdir, 'big.bin')
    with open(big, 'wb') as f:
        f.write(bytes(200 * 1024))                 # 200KB → ~200 帧
    link, dev, sess = make_session()
    box = {'progress': [], 'stages': [], 'failed': [], 'done': False,
           'cancelled': False}
    watch(sess, box)
    assert sess.start(big, flash=0x02, mem=0x12, divide=0,
                      frame_len=1024, frame_num=1) is True
    assert spin_until(app, lambda: len(box['progress']) >= 5), '进度未推进'
    sess.cancel()
    assert spin_until(app, lambda: box['cancelled'] or box['done'], timeout=8.0), \
        '取消未生效'
    assert box['cancelled'], '应为 cancelled 而非 done'
    assert not sess.is_running
    print('E. 传输中取消 OK（已推进 %d 帧后取消）' % len(box['progress']))
    link.close()

    os.remove(fpath)
    os.remove(big)
    print('SMOKE OK')
    QTimer.singleShot(0, app.quit)
    app.exec_()


if __name__ == '__main__':
    main()
