# -*- coding: utf-8 -*-
"""带镜像能力的 Transport 包装（观测层）。

设计要点：
  1. **透传**：所有接口转发给被包装的 transport，参数与异常原样传递，
     不改变任何行为 —— 这是能包装"真机验证通过"资产的前提。
  2. **旁路**：sink 出错一律吞掉，绝不影响串口业务。
  3. **覆盖全部出口**：字节流出口只有 `write` 与 `read_some` 两个；
     `read_exact` / `read_until_idle` 在基类里由 `read_some` 拼装，
     因此包装 `read_some` 即覆盖全部读取路径。
"""

import time

from ..transport.base import Transport
from .sinks import FileSink, UdpSink, format_event

DEFAULT_UDP_PORT = 39527      # 监视窗口默认监听端口
DEFAULT_LOG_DIR = "logs"      # 相对 bmu_testkit 包目录


class MirroredTransport(Transport):
    """包装任意 Transport，把收发投递给 sinks。

    延迟建 sink：`open()` 成功后才真正创建，避免串口打不开时留下空日志。
    """

    def __init__(self, inner: Transport, sinks=None, note_fn=None,
                 sink_factory=None):
        super().__init__(name=inner.name)
        self._inner = inner
        self._sinks = list(sinks or [])
        self._sink_factory = sink_factory      # 延迟建 sink 用
        self._note_fn = note_fn
        self.log_path = None

    # ---------- sinks ----------
    def add_sink(self, sink):
        self._sinks.append(sink)

    def close_sinks(self):
        for s in self._sinks:
            try:
                s.close()
            except Exception:
                pass

    def _emit(self, direction: str, data: bytes, elapsed: float = None):
        """向所有 sink 投递；任何异常都吞掉（观察不得影响业务）。"""
        if not data:
            return
        try:
            note = self._note_fn() if self._note_fn else ""
        except Exception:
            note = ""
        line = format_event(direction, data, note=note, source=self.name,
                            elapsed=elapsed)
        for s in self._sinks:
            try:
                s.emit(line)
            except Exception:
                pass

    # ---------- 透传：生命周期 ----------
    @property
    def is_open(self) -> bool:
        return self._inner.is_open

    def open(self):
        """先开 inner；成功后才建 sink（避免失败时留下空日志）。"""
        result = self._inner.open()
        if self._sink_factory is not None and not self._sinks:
            try:
                sinks, self.log_path = self._sink_factory()
                self._sinks.extend(sinks)
            except Exception:
                self._sink_factory = None       # 建失败就永久放弃，不影响业务
        return result

    def close(self):
        """关闭通道时一并关闭 sinks，保证日志刷盘、UDP 端口释放。"""
        try:
            return self._inner.close()
        finally:
            self.close_sinks()

    # ---------- 透传：收发（镜像点） ----------
    def write(self, data: bytes) -> int:
        t0 = time.monotonic()
        n = self._inner.write(data)
        self._emit("TX", bytes(data), elapsed=time.monotonic() - t0)
        return n

    def read_some(self, timeout=None) -> bytes:
        t0 = time.monotonic()
        chunk = self._inner.read_some(timeout)
        if chunk:
            self._emit("RX", bytes(chunk), elapsed=time.monotonic() - t0)
        return chunk

    # ---------- 透传：其余公开成员 ----------
    def __getattr__(self, item):
        """未显式定义的一律转发给 inner（如 stats / describe / drain_input
        / send_frame / recv_frame 等），避免逐个实现造成遗漏。"""
        return getattr(self._inner, item)


def _session_log_path(log_dir: str = None) -> str:
    import os
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        log_dir or DEFAULT_LOG_DIR)
    name = "serial_trace_%s.log" % time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(base, name)


def attach_mirror(transport: Transport, log_dir: str = None,
                  udp_port: int = DEFAULT_UDP_PORT, note_fn=None,
                  enable_log: bool = True, enable_udp: bool = True,
                  on_ready=None):
    """给 transport 套上镜像层，返回 MirroredTransport。

    sink **延迟到 open() 成功后才创建**：串口打不开时不会留下空日志文件。
    创建完成后通过 `on_ready` 回调把日志路径告知调用方（用于打印提示）。
    """
    if not enable_log and not enable_udp:
        return transport

    def factory():
        sinks = []
        log_path = None
        if enable_log:
            log_path = _session_log_path(log_dir)
            sinks.append(FileSink(log_path))
        if enable_udp:
            sinks.append(UdpSink(port=udp_port))
        if on_ready is not None:
            try:
                on_ready(log_path, udp_port if enable_udp else None)
            except Exception:
                pass
        return sinks, log_path

    return MirroredTransport(transport, sink_factory=factory, note_fn=note_fn)


def attach_mirror_custom(transport: Transport, log_path: str = None,
                         udp_port: int = None, note_fn=None):
    """立即挂载指定 sink（调用方自己给日志路径时用）。

    与 `attach_mirror` 的区别：这里不延迟、不改日志路径命名，
    适合测试或需要固定日志文件名的场景。
    """
    sinks = []
    if log_path:
        sinks.append(FileSink(log_path))
    if udp_port:
        sinks.append(UdpSink(port=udp_port))
    return MirroredTransport(transport, sinks=sinks, note_fn=note_fn)
