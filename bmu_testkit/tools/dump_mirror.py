# -*- coding: utf-8 -*-
"""代替人工的 watch_serial 窗口：监听镜像 UDP 端口，把事件打到终端。

用途：验证 bmu_testkit 的镜像层（FileSink + UdpSink）是否正常工作，
即「agent 跑串口操作时，另一个进程能否实时看到 TX/RX」。

与 watch_serial 的区别：本脚本是纯文本终端输出，不含 PyQt5、不显示配色，
只验证【事件能否收到、字段是否完整】—— 显示层的截断/配色是 watch_serial 的职责。

用法：
    python -m bmu_testkit.tools.dump_mirror --seconds 15
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time

DEFAULT_PORT = 39527


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="监听镜像 UDP 并打印事件")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"镜像 UDP 端口，默认 {DEFAULT_PORT}")
    ap.add_argument("--seconds", type=float, default=15.0,
                    help="监听时长（秒），默认 15")
    ap.add_argument("--truncate", type=int, default=30,
                    help="hex 显示截断字节数，0=全长，默认 30")
    args = ap.parse_args(argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.settimeout(0.3)      # 便于定期检查超时退出

    print(f"[dump_mirror] 监听 UDP 127.0.0.1:{args.port}，"
          f"时长 {args.seconds}s，截断 {args.truncate}B")
    print("-" * 74)

    t0 = time.monotonic()
    n_evt = 0
    srcs = {}

    while (time.monotonic() - t0) < args.seconds:
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue

        line = data.decode("utf-8", "replace").strip()
        if not line:
            continue

        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            print(f"  [非 JSON] {line[:80]}")
            continue

        n_evt += 1
        src = e.get("src", "?")
        srcs[src] = srcs.get(src, 0) + 1

        d = e.get("dir", "??")
        n = e.get("n", 0)
        hx = e.get("hex", "")
        if args.truncate and len(hx) > args.truncate * 3:
            shown = hx[: args.truncate * 3].rstrip() + " ..."
        else:
            shown = hx

        arrow = "TX ->" if d == "TX" else "RX <-"
        print(f"  {e.get('ts','??:??:??.???')}  [{src:>8}]  {arrow} {n:>5}B  {shown}")

    sock.close()
    print("-" * 74)
    print(f"[dump_mirror] 共收到 {n_evt} 个事件")
    if srcs:
        for k, v in sorted(srcs.items()):
            print(f"    通道 {k!r}: {v} 个事件")
    else:
        print("    (没有收到任何事件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
