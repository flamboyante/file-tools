# -*- coding: utf-8 -*-
"""bmu_testkit 命令行入口（CLI 是薄封装，真正的资产是下面的 Python API）。

用法：
    python -m bmu_testkit.cli scan
    python -m bmu_testkit.cli raw   --preset self --port COM10 --hex "EB 90 01 80"
    python -m bmu_testkit.cli heart --preset self --port COM10

超时说明：默认**不超时**（阻塞等待），只记录耗时 —— 便于观察真实时序与定位问题。
需要设上限时用 --timeout 3（秒）。

镜像说明：串口收发默认镜像到日志文件并广播到 UDP 端口，供人用监视窗口实时观察。
监视窗口：python -m bmu_testkit.watch_serial
用 --no-mirror 关闭；--mirror-port 指定 UDP 端口。
"""

import argparse
import json
import os
import sys
import time

import serial.tools.list_ports

from .core.filetransfer import FileTransfer
from .mirror import DEFAULT_UDP_PORT, attach_mirror, parse_event
from .protocol import Ycyk422Protocol
from .transport import SerialTransport

# 未指定 --file 时的候选（挑工程里的小文本文件，避免误拿大文件）
_DEFAULT_FILE_CANDIDATES = ("README.md", "readme", "升级记录.txt")

# 现场参数（用户 2026-09-17 确认）
PRESETS = {
    "debug": {"baudrate": 115200, "parity": "N", "bytesize": 8, "stopbits": 1},
    "self": {"baudrate": 921600, "parity": "O", "bytesize": 8, "stopbits": 1},
    "sc": {"baudrate": 921600, "parity": "O", "bytesize": 8, "stopbits": 1},
}


def _make_transport(args) -> SerialTransport:
    params = dict(PRESETS[args.preset]) if args.preset else {
        "baudrate": args.baud, "parity": args.parity,
        "bytesize": args.bytesize, "stopbits": args.stopbits,
    }
    if args.baud is not None:
        params["baudrate"] = args.baud
    if args.parity is not None:
        params["parity"] = args.parity
    t = SerialTransport(port=args.port, timeout=args.timeout,
                        name=args.preset or args.port, **params)
    return _mirror(t, args)


def _mirror(transport, args):
    """给通道套上镜像层。默认开启：日志落盘 + UDP 广播，供监视窗口实时观察。

    sink 在串口打开成功后才创建，因此打不开串口时不会留下空日志。
    """
    if getattr(args, "no_mirror", False):
        return transport
    port = getattr(args, "mirror_port", None) or DEFAULT_UDP_PORT

    def on_ready(log_path, udp_port):
        print("=" * 58)
        if log_path:
            print("[镜像] 完整日志: %s" % log_path)
        if udp_port:
            print("[镜像] 实时观察: python -m bmu_testkit.watch_serial --port %d"
                  % udp_port)
        print("=" * 58)

    return attach_mirror(transport, udp_port=port,
                         note_fn=lambda: getattr(args, "cmd", ""),
                         on_ready=on_ready)


def cmd_scan(args):
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("未发现串口")
        return 0
    print(f"发现 {len(ports)} 个串口：")
    for p in ports:
        print(f"  {p.device:<8} | {p.description}")
        if args.verbose and p.hwid:
            print(f"           hwid: {p.hwid}")
    return 0


def cmd_raw(args):
    """L1 通用传输：发任意字节流。"""
    if not args.recv_only and not args.hex:
        print("需要 --hex（要发的字节）或 --recv-only（只收不发）", file=sys.stderr)
        return 2
    data = b""
    if args.hex:
        try:
            data = bytes.fromhex(args.hex.replace(" ", "").replace("-", ""))
        except ValueError as e:
            print(f"hex 解析失败: {e}", file=sys.stderr)
            return 2
    t = _make_transport(args)
    with t:
        print(f"[{t.describe()}]")
        dropped = t.drain_input()
        if dropped:
            print(f"  清掉输入缓冲残留 {dropped} 字节")
        if args.recv_only:
            print("仅接收模式，等待数据…")
            t0 = time.monotonic()
            resp = t.read_until_idle(idle=args.idle, max_bytes=args.max_bytes,
                                     timeout=args.timeout)
            print(f"RX 等了 {time.monotonic() - t0:.3f}s, {len(resp)}B: "
                  f"{resp.hex(' ')}")
            print(f"统计: {t.stats}")
            return 0
        t0 = time.monotonic()
        n = t.write(data)
        print(f"TX {n}B: {data.hex(' ')}")
        if args.no_read:
            return 0
        resp = t.read_until_idle(idle=args.idle, max_bytes=args.max_bytes,
                                 timeout=args.timeout)
        print(f"RX 等了 {time.monotonic() - t0:.3f}s, {len(resp)}B: {resp.hex(' ')}")
        print(f"统计: {t.stats}")
    return 0


def cmd_heart(args):
    """self 422 通路探测：发心跳，等 MCU 应答（期望 IRCode 0x001F）。"""
    proto = Ycyk422Protocol()
    t = _make_transport(args)
    with t:
        print(f"[{t.describe()}]")
        dropped = t.drain_input()
        if dropped:
            print(f"  清掉输入缓冲残留 {dropped} 字节")
        for i in range(1, args.count + 1):
            frame = proto.build_heartbeat()
            t0 = time.monotonic()
            t.write(frame)
            print(f"\n#{i} TX {len(frame)}B: {frame.hex(' ')}")
            resp = t.read_until_idle(idle=args.idle, max_bytes=args.max_bytes,
                                     timeout=args.timeout)
            elapsed = time.monotonic() - t0
            if not resp:
                print(f"   RX: 无应答（等了 {elapsed:.3f}s）")
                continue
            print(f"   RX 等了 {elapsed:.3f}s, {len(resp)}B: {resp.hex(' ')}")
            info = proto.decode_response(resp)
            for k in ("ircode_at_8", "type_at_9", "type_label",
                      "result_at_10", "result_label"):
                if k in info:
                    print(f"      {k}: {info[k]}")
        print(f"\n统计: {t.stats}")
        print(f"明细: {json.dumps(t.stats.as_dict(), ensure_ascii=False)}")
    return 0


def _pick_default_file():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in _DEFAULT_FILE_CANDIDATES:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            return p
    return None


def cmd_file_transfer(args):
    """422 文件传输（危险：会真实擦除目标分区，默认二次确认 + 传输中防 Ctrl+C）。"""
    file_path = args.file or _pick_default_file()
    if not file_path or not os.path.isfile(file_path):
        print(f"文件不可用: {file_path}（用 --file 指定）", file=sys.stderr)
        return 2
    try:
        flash = int(args.flash, 0)
        mem = int(args.mem, 0)
    except ValueError as e:
        print(f"flash/mem 解析失败（支持 0xFA 或 250 两种写法）: {e}", file=sys.stderr)
        return 2

    t = _make_transport(args)
    ft = FileTransfer(t, on_log=lambda m: print(m))
    with t:
        print(f"[{t.describe()}]")
        r = ft.transfer(file_path, flash, mem, divide=args.divide,
                        frame_len=args.frame_len, frame_num=args.frame_num,
                        require_confirm=not args.yes, timeout=args.timeout,
                        do_refactor=not args.no_refactor)
    print()
    print(r)
    print(f"统计: {t.stats}")
    print(f"明细: {json.dumps(t.stats.as_dict(), ensure_ascii=False)}")
    return 0 if r.ok else 1


def cmd_can(args):
    """CAN 通路收发（L1：任意 ID + 任意数据，不含指令语义）。"""
    from JiangCan_Tools.ECAN import BaudRate      # 延迟导入，避免启动即依赖 CAN 库
    from .transport import CanMedia

    ch = 0 if args.channel.upper() == "A" else 1
    baud = getattr(BaudRate, f"BAUD_{args.baud.upper()}", BaudRate.BAUD_500K)
    m = CanMedia(channel=ch, baud=baud, default_id=args.id,
                 dll_path=args.dll, name=f"CAN-{args.channel.upper()}")
    try:
        m.open()
    except Exception as e:
        print(f"CAN 打开失败: {e}", file=sys.stderr)
        return 1

    try:
        print(f"[{m.describe()}]")
        if args.data:
            try:
                data = bytes.fromhex(args.data.replace(" ", "").replace("-", ""))
            except ValueError as e:
                print(f"hex 解析失败: {e}", file=sys.stderr)
                return 2
            print(f"TX ID=0x{args.id:X} 共 {len(data)} 字节 "
                  f"(send_type={args.send_type})")
            for i in range(0, len(data), 8):
                chunk = data[i:i + 8]
                ok = m.send_frame(args.id, chunk, send_type=args.send_type)
                print(f"   帧{i // 8 + 1}: {chunk.hex(' ')} -> "
                      f"{'OK' if ok else '发送失败/超时（检查总线节点与终端电阻）'}")
            if args.no_recv:
                return 0

        print(f"等待接收（timeout={args.timeout}）…")
        frames = m.recv_frame(timeout=args.timeout)
        if not frames:
            print("   无数据")
            return 0
        for fid, d in frames:
            print(f"   RX ID=0x{fid:X} ({len(d)}B): {d.hex(' ')}")
        print(f"统计: {m.stats}")
    finally:
        m.close()
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="bmu_testkit",
        description="MCU 下位机上位机测试基础设施（L1 传输 + L2 指令）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="列出可用串口")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_scan)

    def add_common(sp):
        sp.add_argument("--port", required=True, help="串口号，如 COM10")
        sp.add_argument("--preset", choices=sorted(PRESETS),
                        help="通道预设：debug=115200 8N1 / self,sc=921600 8O1")
        sp.add_argument("--baud", type=int, default=None, help="覆盖波特率")
        sp.add_argument("--parity", default=None, help="覆盖校验位 N/O/E")
        sp.add_argument("--bytesize", type=int, default=8)
        sp.add_argument("--stopbits", type=float, default=1)
        sp.add_argument("--timeout", type=float, default=None,
                        help="总超时秒数；默认 None=不超时（只记耗时）")
        sp.add_argument("--idle", type=float, default=0.3,
                        help="静默判定时长（秒），默认 0.3")
        sp.add_argument("--max-bytes", type=int, default=4096)
        sp.add_argument("--no-mirror", action="store_true",
                        help="关闭串口镜像（默认开启：日志 + UDP 广播）")
        sp.add_argument("--mirror-port", type=int, default=None,
                        help="镜像 UDP 端口，默认 %d" % DEFAULT_UDP_PORT)

    r = sub.add_parser("raw", help="L1：发送任意字节流")
    add_common(r)
    r.add_argument("--hex", default=None, help='待发字节，如 "EB 90 01 80"')
    r.add_argument("--recv-only", action="store_true",
                   help="只收不发（配合虚拟串口对做通路测试）")
    r.add_argument("--no-read", action="store_true", help="只发不收")
    r.set_defaults(func=cmd_raw)

    h = sub.add_parser("heart", help="self 422 心跳探测（等 0x001F 应答）")
    add_common(h)
    h.add_argument("--count", type=int, default=1, help="发几次，默认 1")
    h.set_defaults(func=cmd_heart)

    f = sub.add_parser("file-transfer",
                       help="422 文件传输（危险：真实擦除分区）")
    add_common(f)
    f.add_argument("--file", default=None,
                   help="待传文件路径；省略则自动挑工程里的小文本文件")
    f.add_argument("--flash", required=True, help="flash 参数，如 0xFA")
    f.add_argument("--mem", required=True, help="mem 参数，如 0x20")
    f.add_argument("--frame-len", type=int, default=1000)
    f.add_argument("--frame-num", type=int, default=100)
    f.add_argument("--divide", action="store_true", help="分段传输")
    f.add_argument("--no-refactor", action="store_true", help="传完不发起重构")
    f.add_argument("--yes", action="store_true", help="跳过二次确认（慎用）")
    f.set_defaults(func=cmd_file_transfer)

    c = sub.add_parser("can", help="CAN 通路收发（L1：任意 ID + 任意数据）")
    c.add_argument("--channel", choices=["A", "B", "a", "b"], default="A",
                   help="CAN A / CAN B，默认 A")
    c.add_argument("--id", type=lambda s: int(s, 0), default=0,
                   help="CAN ID，如 0x31801")
    c.add_argument("--data", default=None,
                   help='待发数据 hex，如 "00 25 25"；省略则只收不发')
    c.add_argument("--baud", default="500K",
                   help="1M/800K/500K/250K/125K/100K，默认 500K")
    c.add_argument("--dll", default=None, help="ECanVci64.dll 路径（默认取 dist 下）")
    c.add_argument("--timeout", type=float, default=3.0, help="接收等待秒数")
    c.add_argument("--send-type", type=int, default=0,
                   help="0 正常(总线无节点会阻塞) / 1 单次不重发 / "
                        "2 自发自收 / 3 单次自发自收（自检，不需外部节点）")
    c.add_argument("--no-recv", action="store_true", help="只发不收")
    c.set_defaults(func=cmd_can)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
