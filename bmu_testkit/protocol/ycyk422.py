# -*- coding: utf-8 -*-
"""422 指令层（L2）—— 复用工程现有组帧逻辑，不重写一遍。

组帧全部走 `ycyk_422.Ycyk_422_Work`，这里只做薄封装，避免两套逻辑漂移。

## 帧结构（2026-09-18 实测确认，非推测）

请求帧（发往 self 422）：
    [0:2]   帧头 EB 90
    [2:4]   apid
    [4:6]   控制位 + 序列计数
    [6:8]   数据域长度
    [8:10]  IRCode（指令码）
    [10:12] 校验和

应答帧（self 422 口返回）：
    **帧头固定为 1A CF** —— 与请求帧头 EB 90 不同，协议不对称，已由用户实测确认。
    其余字段布局与请求一致。

校验和算法（已用真实应答 `1A CF 01 87 C0 62 00 01 00 1F FE 35` 验证通过）：
    从 index 2 起、到校验字段之前，逐字节累加 → 取反 → & 0xFFFF（16 位大端）
"""

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ycyk_422 import Ycyk_422_Work  # noqa: E402  工程现有协议层

# ---------- 帧头 ----------
REQ_HEADER = b"\xEB\x90"    # 请求帧头（422）
ACK_HEADER = b"\x1A\xCF"    # 应答帧头（self 422 口固定为此值）

# ---------- 心跳（文档 11.3-1） ----------
HEARTBEAT_CMD = 0x001D
HEARTBEAT_ACK = 0x001F

# ---------- 文件传输应答类型码（沿用 Serial_thread.RESPONSE_LABELS） ----------
RESPONSE_LABELS = {
    0x5A: "文件传输开始应答",
    0x8A: "文件传输应答",
    0xBB: "文件传输结束应答",
    0xCA: "重构结果查询应答",
}

# 结果码（位于应答帧 resp[10]）
RESULT_OK = 0x00
RESULT_ERR = 0xFF
RESULT_CRC_ERR = 0x11

RESULT_LABELS = {
    RESULT_OK: "成功",
    RESULT_ERR: "异常",
    RESULT_CRC_ERR: "CRC 重构异常",
}


def checksum(body: bytes) -> int:
    """422 校验和：逐字节累加 → 取反 → 取低 16 位。

    body 指「从 index 2 起、到校验字段之前」的那段（即 resp[2:-2]）。
    """
    acc = 0
    for b in body:
        acc += b
    return (~acc) & 0xFFFF


class Ycyk422Protocol:
    """422 协议封装（当前指令格式）。将来换协议就换这个类。"""

    def __init__(self, worker=None):
        self.worker = worker or Ycyk_422_Work(id=0xEB90)

    # ---------- 组帧 ----------
    def build_heartbeat(self) -> bytes:
        return bytes(self.worker.send_heart())

    def build_reboot(self) -> bytes:
        return bytes(self.worker.Send_Reboot())

    def build_version_check(self) -> bytes:
        return bytes(self.worker.Send_VersionCheck())

    # ---------- 解析（严格，基于实测） ----------
    @staticmethod
    def decode_response(resp: bytes, expect_header: bytes = ACK_HEADER) -> dict:
        """解析应答帧，每一项都给出是否通过校验。"""
        out = {
            "length": len(resp),
            "hex": resp.hex(" "),
        }
        if len(resp) < 12:
            out["error"] = f"应答长度不足 12 字节（实际 {len(resp)}）"
            return out

        header = bytes(resp[:2])
        out["header"] = header.hex(" ")
        out["header_ok"] = (header == expect_header)
        if not out["header_ok"]:
            out["header_expected"] = expect_header.hex(" ")

        out["apid"] = resp[2:4].hex(" ")
        out["seq"] = resp[4:6].hex(" ")
        out["data_len"] = int.from_bytes(resp[6:8], "big")

        ircode = int.from_bytes(resp[8:10], "big")
        out["ircode"] = hex(ircode)
        out["is_heartbeat_ack"] = (ircode == HEARTBEAT_ACK)
        out["file_type_label"] = RESPONSE_LABELS.get(resp[9])

        calc = checksum(resp[2:-2])
        actual = int.from_bytes(resp[-2:], "big")
        out["checksum_calc"] = hex(calc)
        out["checksum_actual"] = hex(actual)
        out["checksum_ok"] = (calc == actual)

        return out

    @staticmethod
    def is_heartbeat_ack(resp: bytes) -> bool:
        """心跳应答判定：IRCode == 0x001F。"""
        return len(resp) >= 10 and int.from_bytes(resp[8:10], "big") == HEARTBEAT_ACK


# ---------- 帧长计算（关键：不同指令应答长度不同，必须算而不是猜） ----------
# 规则由用户实测给出并已验证：
#   第 7、8 字节（即 resp[6:8]）= 数据域长度 - 1
#   => 数据域字节数 = resp[6:8]的值 + 1
#   => 总帧长      = 8(头部) + 数据域 + 2(校验和)
# 验证：心跳应答 1A CF 01 87 C0 62 00 01 00 1F FE 35
#       resp[6:8]=00 01 → 数据域 2 字节 → 8+2+2 = 12 == 实际长度 ✓
# 推论：文件传输应答数据域 3 字节 → 总长 13（与现有代码 LengthRecv=13 吻合）

HEAD_LEN = 8        # 帧头（含长度字段）长度
CHECKSUM_LEN = 2    # 校验和长度


def data_len_from_head(head: bytes) -> int:
    """由前 8 字节推出数据域字节数。"""
    if len(head) < HEAD_LEN:
        raise ValueError(f"头部不足 {HEAD_LEN} 字节（实际 {len(head)}）")
    return int.from_bytes(head[6:8], "big") + 1


def frame_total_len(head: bytes) -> int:
    """由前 8 字节推出整帧长度。"""
    return HEAD_LEN + data_len_from_head(head) + CHECKSUM_LEN


def read_frame(transport, timeout=None, header: bytes = ACK_HEADER,
               max_sync: int = 128) -> bytes:
    """精确读取一个应答帧（**不预设长度**）。

    步骤：同步到帧头 → 读满 8 字节 → 用长度字段算出总长 → 读剩余。
    这样任意数据域长度的帧都能正确接收。
    """
    # 注意：底层 read_some 常常**一次返回整帧**（串口缓冲区里已堆积完整报文），
    # 所以不能假设「每次只读到 1 个字节」，必须在缓冲区里**查找帧头**，而不是检查末尾。
    started = time.monotonic()
    buf = bytearray()
    while header not in bytes(buf):               # 1. 累积到包含帧头
        chunk = transport.read_some(timeout=timeout)
        if not chunk:
            raise ValueError(
                f"等待帧头 {header.hex(' ')} 超时：已收 {len(buf)} 字节 "
                f"({bytes(buf).hex(' ')})")
        buf += chunk
        if len(buf) > max_sync:
            raise ValueError(
                f"同步帧头失败：{len(buf)} 字节内未见 {header.hex(' ')}，"
                f"开头 32 字节: {bytes(buf[:32]).hex(' ')}")
    idx = bytes(buf).find(header)                 # 2. 丢弃帧头之前的噪声
    if idx > 0:
        buf = buf[idx:]
    while len(buf) < HEAD_LEN:                    # 3. 补齐前 8 字节
        buf += transport.read_exact(HEAD_LEN - len(buf), timeout=timeout)
    total = frame_total_len(bytes(buf[:HEAD_LEN]))   # 4. 按长度字段算总长
    if len(buf) < total:                              # 只补缺口（数据可能已全部到达）
        buf += transport.read_exact(total - len(buf), timeout=timeout)
    # 记录收帧耗时：read_some 本身不记统计，这里补上，保证「历史计时」可用
    if getattr(transport, "stats", None) is not None:
        transport.stats.record(time.monotonic() - started, total)
    # 超出 total 的部分属于后续帧，此处丢弃；本函数面向「一问一答」场景
    return bytes(buf[:total])
