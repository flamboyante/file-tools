# -*- coding: utf-8 -*-
"""ycyk_framing · 422 应答帧组装器（字节流 → 完整帧）。

════════════════════════════════════════════════════════════════
为什么存在（老 bug 清单 #2+#3 的埋葬处）
════════════════════════════════════════════════════════════════
旧 Serial_thread 的等应答是 `recv(13)` 死等 13 字节。但 422 应答帧
**长度不固定**：文件传输类应答 13 字节（数据域 3），心跳应答 12 字节
（数据域 2）。recv(13) 撞上 12 字节心跳应答 = 永久死锁。

真规则（用户实测，bmu_testkit 真机验证过 21/21）：

    resp[6:8] 的值 = 数据域长度 - 1
    总帧长 = 8(头部，含长度字段) + 数据域 + 2(校验和)

本组装器：同步到 `1A CF` 帧头 → 收满 8 字节 → 用 frame_total_len()
**从帧头算出总长** → 收满剩余。任何长度的心跳/传输应答都不会卡死。

帧长计算函数直接 import bmu_testkit（单一事实源，禁止复制——
12/13 字节的分歧就是当年两处各写一套造成的）。
"""
from bmu_testkit.protocol.ycyk422 import ACK_HEADER, frame_total_len

HEAD_LEN = 8
MAX_BUF = 4096           # 缓冲上限：超过说明流错乱，丢弃重新同步
MAX_FRAME = 1200         # 单帧上限（帧长字段理论最大 8+256+2）


class FrameAssembler(object):
    """feed 字节块，吐完整应答帧。线程安全：内部一把锁。

    用法（在 link.rx 的槽里）：
        for frame in assembler.feed(data):
            ack_q.put(frame)
    """

    def __init__(self):
        self._buf = bytearray()
        self._lock = __import__('threading').Lock()

    def feed(self, data):
        """喂入字节块，返回完整帧列表（0 个或多个）。"""
        out = []
        with self._lock:
            self._buf.extend(data)
            if len(self._buf) > MAX_BUF:
                # 流错乱保护：丢掉旧数据重新找同步头
                del self._buf[:len(self._buf) - len(ACK_HEADER)]
            while True:
                frame = self._try_extract()
                if frame is None:
                    break
                out.append(frame)
        return out

    def _try_extract(self):
        """从缓冲里切出一个完整帧；不足或无同步头返回 None。"""
        buf = self._buf
        # 1. 同步到帧头
        idx = buf.find(ACK_HEADER)
        if idx < 0:
            # 保留最后 len(ACK_HEADER)-1 字节（半截头可能在下一块到）
            if len(buf) > len(ACK_HEADER) - 1:
                del buf[:len(buf) - (len(ACK_HEADER) - 1)]
            return None
        if idx:
            del buf[:idx]                       # 丢掉同步头前的杂散字节

        # 2. 头都不够，等下一块
        if len(buf) < HEAD_LEN:
            return None

        # 3. 按帧头算总长（12/13/任意，不再是猜的 13）
        try:
            total = frame_total_len(bytes(buf[:HEAD_LEN]))
        except (ValueError, IndexError):
            # 长度字段非法：当前同步头作废，跳过 1 字节重新同步
            del buf[:1]
            return None
        if total > MAX_FRAME:
            del buf[:1]
            return None

        # 4. 整帧没到齐，等下一块
        if len(buf) < total:
            return None

        frame = bytes(buf[:total])
        del buf[:total]
        return frame
