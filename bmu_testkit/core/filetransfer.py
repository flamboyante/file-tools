# -*- coding: utf-8 -*-
"""422 文件传输（重构升级）流程。

对外只暴露 `transfer(file_path, flash, mem, ...)` —— **传路径，不传字节流**。
文件读取、分段分帧、逐帧等应答、结果判定，全部是这里内部的职责。

⚠️ 危险操作：会真实擦除目标 Flash 分区。中断会留下空白分区，因此：
   - 默认要求二次确认（`require_confirm`）
   - 传输进行中忽略 Ctrl+C（SIGINT 保护），避免半途而废
"""

import os
import signal
import time
from dataclasses import dataclass

from ..protocol.ycyk422 import (
    ACK_HEADER,
    RESPONSE_LABELS,
    RESULT_LABELS,
    Ycyk422Protocol,
    read_frame,
)
from ..transport.base import TransportTimeout

# 不同指令的应答帧长并不相同（已知心跳应答 12 字节，文件传输应答长度未实测）。
# 因此**不能用固定长度读帧**：默认走「读到线路静默 + 按帧头切分」，通吃任意长度。
# 只有在明确知道某类应答确切长度时，才传 expect_len 走精确读取。
FILE_RESP_LEN = None          # None = 自动（推荐）
DEFAULT_IDLE = 0.15           # 静默判定：连续这么久没新数据即认为一帧结束
DEFAULT_MAX_POLL = 20         # 最多轮询多少批仍未等到期望帧

TYPE_BEGIN = 0x5A           # 文件传输开始应答
TYPE_DATA = 0x8A            # 文件传输（每帧）应答
TYPE_FINISH = 0xBB          # 文件传输结束应答
TYPE_REFACTOR_RESULT = 0xCA  # 重构结果查询应答

DEFAULT_FRAME_LEN = 1000    # 用户指定
DEFAULT_FRAME_NUM = 100     # 用户指定


@dataclass
class TransferResult:
    ok: bool
    path: str = ""
    file_size: int = 0
    frames_sent: int = 0
    bytes_sent: int = 0
    elapsed_s: float = 0.0
    stage: str = ""              # 到达的阶段
    error: str = ""
    last_response_hex: str = ""

    def __str__(self):
        if self.ok:
            return (f"传输成功: {os.path.basename(self.path)} "
                    f"({self.bytes_sent}/{self.file_size} 字节, {self.frames_sent} 帧, "
                    f"{self.elapsed_s:.2f}s)")
        return f"传输失败 [{self.stage}]: {self.error}"


class FileTransferError(Exception):
    """文件传输过程中的协议级错误（固件回了异常结果码等）。"""


class FileTransfer:
    """422 文件传输。构造只依赖 Transport（L1），不关心底层是串口还是别的。"""

    def __init__(self, transport, protocol=None, on_log=None, on_progress=None):
        self.t = transport
        self.p = protocol or Ycyk422Protocol()
        self.on_log = on_log or (lambda m: None)
        self.on_progress = on_progress or (lambda sent, total: None)
        self._in_transfer = False
        self._orig_sigint = None
        # begin 应答后给固件的准备时间（对齐现有 Serial_thread 的 time.sleep(1)）
        self.begin_settle_s = 1.0

    # ---------- SIGINT 保护 ----------
    def _install_sigint_guard(self):
        def handler(signum, frame):
            if self._in_transfer:
                self.on_log("!! 传输进行中，已忽略 Ctrl+C —— 中断会留下空白 Flash 分区。")
                self.on_log("   请等待本轮传输结束；确需中止请先确认分区状态。")
                return
            raise KeyboardInterrupt
        try:
            self._orig_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, handler)
        except (ValueError, AttributeError, OSError):
            # 非主线程或不支持 signal 的环境：降级为不装保护，别把传输搞崩
            self._orig_sigint = None
            self.on_log("(提示) 当前环境无法安装 Ctrl+C 保护，传输过程中请勿中断。")

    def _restore_sigint(self):
        if self._orig_sigint is not None:
            signal.signal(signal.SIGINT, self._orig_sigint)
            self._orig_sigint = None

    # ---------- 应答等待 ----------
    @staticmethod
    def _iter_frames(buf: bytes):
        """按应答帧头切分报文 —— 兼容任意帧长，不依赖预设长度。

        一帧 = 从一个帧头起，到下一个帧头（或缓冲区末尾）止。
        """
        idx = 0
        while True:
            i = buf.find(ACK_HEADER, idx)
            if i < 0:
                return
            j = buf.find(ACK_HEADER, i + len(ACK_HEADER))
            end = j if j >= 0 else len(buf)
            yield buf[i:end]
            idx = end

    def _wait_type(self, expect_type, timeout=None, expect_len=None,
                   idle=DEFAULT_IDLE, max_poll=DEFAULT_MAX_POLL) -> bytes:
        """等指定类型码的应答。

        默认**不预设帧长**：读到线路静默为止，再按帧头切分，因此 12/13/20 字节
        通吃。若明确知道某类应答的确切长度，传 `expect_len` 走精确读取（更快更严）。
        类型码不匹配的帧一律**跳过**（串口上混有其他帧）。
        """
        label = RESPONSE_LABELS.get(expect_type, hex(expect_type))
        fixed = expect_len if expect_len is not None else FILE_RESP_LEN

        for _ in range(max_poll):
            # 用帧头长度字段精确收帧，兼容任意数据域长度
            try:
                frame = read_frame(self.t, timeout=timeout)
            except ValueError as e:
                self.on_log(f"   收帧异常，跳过: {e}")
                continue
            got = frame[9]
            if got != expect_type:
                self.on_log(f"   跳过无关应答: 期望 {label}, 实收 "
                            f"{RESPONSE_LABELS.get(got, hex(got))} ({frame.hex(' ')})")
                continue
            result = frame[10]
            if result == 0x00:
                return frame
            raise FileTransferError(
                f"{label} 返回异常结果码 {hex(result)}"
                f"（{RESULT_LABELS.get(result, '未定义')}），原始帧: {frame.hex(' ')}")
        raise TimeoutError(f"等 {label} 超时（轮询 {max_poll} 批仍未等到）")

    # ---------- 主流程 ----------
    def transfer(self, file_path: str, flash: int, mem: int, divide: bool = False,
                 frame_len: int = DEFAULT_FRAME_LEN,
                 frame_num: int = DEFAULT_FRAME_NUM,
                 require_confirm: bool = True, confirm_cb=None,
                 timeout=None, do_refactor: bool = True) -> TransferResult:
        """传一个文件到指定 flash/mem。

        参数中的 flash / mem 是业务语义（哪个 Flash、哪个分区），由调用方给定，
        本模块不做猜测。
        """
        res = TransferResult(ok=False, path=file_path)
        if not os.path.isfile(file_path):
            res.error = f"文件不存在: {file_path}"
            return res
        res.file_size = os.path.getsize(file_path)

        if require_confirm:
            tip = (f"即将传输文件:\n"
                   f"  文件 : {file_path}\n"
                   f"  大小 : {res.file_size} 字节\n"
                   f"  flash: {hex(flash)}  mem: {hex(mem)}\n"
                   f"  帧长 : {frame_len}  帧数: {frame_num}  分段: {divide}")
            ok = confirm_cb(tip) if confirm_cb else self._default_confirm(tip)
            if not ok:
                res.error = "用户取消"
                res.stage = "确认"
                return res

        w = self.p.worker
        w.if_file_divide = 0x03 if divide else 0x00
        w.frame_size = frame_len
        w.frames = frame_num

        started = time.monotonic()
        self._install_sigint_guard()
        self._in_transfer = True
        try:
            # --- 阶段 1：开始帧 ---
            res.stage = "begin"
            self.on_log("[begin] 发送文件传输开始帧")
            begin = bytes(w.send_begin(0x18, file_path, flash, mem,
                                       w.if_file_divide, frame_len, frame_num))
            self.t.write(begin)
            resp = self._wait_type(TYPE_BEGIN, timeout=timeout)
            res.last_response_hex = resp.hex(" ")
            self.on_log(f"[begin] 收到开始应答 OK ({resp.hex(' ')})")
            if self.begin_settle_s > 0:
                # 对齐现有实现：固件收到开始指令后需要时间准备（可能触发擦除）
                self.on_log(f"[begin] 等待 {self.begin_settle_s}s 让固件准备")
                time.sleep(self.begin_settle_s)

            # --- 阶段 2：数据帧，每帧等 0x8A ---
            res.stage = "data"
            total = res.file_size
            with open(file_path, "rb") as f:
                for seg in range(w.segments):
                    frames = (w.segments_end_frames if seg == w.segments - 1
                              else w.frames)
                    self.on_log(f"[data] 第 {seg + 1}/{w.segments} 段，{frames} 帧")
                    for i in range(frames):
                        data = f.read(frame_len)
                        if not data:
                            break
                        if frames == 1:
                            gf = 3          # 单帧
                        elif i == 0:
                            gf = 1          # 首帧
                        elif i == frames - 1:
                            gf = 2          # 尾帧
                        else:
                            gf = 0          # 中间帧
                        frame = bytes(w.send_datas(0x18, seg, gf, data))
                        self.t.write(frame)
                        resp = self._wait_type(TYPE_DATA, timeout=timeout)
                        res.frames_sent += 1
                        res.bytes_sent += len(data)
                        res.last_response_hex = resp.hex(" ")
                        self.on_progress(res.bytes_sent, total)

            # --- 阶段 3：结束帧（收到 0xBB 即判成功） ---
            res.stage = "finish"
            self.on_log("[finish] 发送结束帧")
            self.t.write(bytes(w.send_finish(0x18)))
            resp = self._wait_type(TYPE_FINISH, timeout=timeout)
            res.last_response_hex = resp.hex(" ")
            self.on_log(f"[finish] 收到结束应答 OK ({resp.hex(' ')})")

            # --- 阶段 4：发起重构（不等结果） ---
            if do_refactor:
                res.stage = "refactor"
                self.on_log("[refactor] 发起重构（不等待结果）")
                self.t.write(bytes(w.refactor_begin(0x18, flash, mem)))

            res.stage = "done"
            res.ok = True
        except (TransportTimeout, TimeoutError) as e:
            res.error = str(e)
        except FileTransferError as e:
            res.error = str(e)
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
        finally:
            res.elapsed_s = time.monotonic() - started
            self._in_transfer = False
            self._restore_sigint()
        return res

    @staticmethod
    def _default_confirm(tip: str) -> bool:
        print(tip)
        try:
            return input("确认执行？[y/N] ").strip().lower() == "y"
        except EOFError:
            return False
