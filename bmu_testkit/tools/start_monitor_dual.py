# -*- coding: utf-8 -*-
"""双窗启动器：依次拉起两个监视窗口，并逐个确认是否真的起来了。

为什么不用 .bat 里连写两条 `start`：
  - cmd 的 `start` 对 GUI 程序（pythonw）行为不稳定，且无法回读子进程状态
  - 窗口起没起来，只能靠外部观察（netstat / tasklist），bat 做不到
  - bat 的行尾（CRLF）与编码（ASCII）都是额外坑

本脚本用 subprocess 逐个拉起 + 轮询校验 UDP 端口是否真的被 bind，
每步结果都打印出来 —— 失败时能直接看到是哪一个窗、错在哪。

用法：
    D:\\Anaconda3\\envs\\pyqt_side_all_0328\\python.exe bmu_testkit\\tools\\start_monitor_dual.py
    ... --ports 39527 39528          # 自定义端口
    ... --views hex ascii            # 自定义视图
"""

from __future__ import print_function

import argparse
import io
import os
import subprocess
import sys
import time

if sys.version_info[0] >= 3:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))

# pythonw: 无控制台，适合 GUI；失败时看不到报错，所以下面用 python 做诊断兜底
PYW_CANDIDATES = [
    r"D:\Anaconda3\envs\pyqt_side_all_0328\pythonw.exe",
    r"D:\Anaconda3\envs\pyqt_side_all_0328\python.exe",
]

DEFAULT_PORTS = (39527, 39528)
DEFAULT_VIEWS = ("hex", "ascii")


def find_pythonw():
    for p in PYW_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def port_in_use(port):
    """用 netstat 查端口是否被监听（不 bind，避免自己占用）。"""
    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "UDP"],
                                      stderr=subprocess.STDOUT)
    except Exception:
        return None
    text = out.decode("utf-8", "replace")
    return ("127.0.0.1:%d" % port) in text


def launch(pyw, port, view, title):
    """拉起一个窗口，返回 (ok, detail)。"""
    cmd = [pyw, "-m", "bmu_testkit.watch_serial",
           "--port", str(port), "--view", view, "--title", title]
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(cmd, cwd=PROJ, creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
    except Exception as exc:
        return False, "Popen 失败: %r" % (exc,)

    # 轮询确认端口被 bind（最多 6 秒）
    for _ in range(30):
        time.sleep(0.2)
        if port_in_use(port):
            return True, "端口 %d 已监听" % port
    return False, "拉起后 6 秒内端口 %d 未被监听" % port


def diagnose(pyw, port, view):
    """窗口没起来时，前台跑一次，把真实报错打出来。"""
    print("   诊断：前台运行以捕获报错 ...")
    cmd = [pyw, "-c",
           "import sys; sys.argv=['x','--port','%d','--view','%s'];"
           "from bmu_testkit.watch_serial import main; main(sys.argv[1:])" % (port, view)]
    try:
        p = subprocess.run(cmd, cwd=PROJ, capture_output=True, timeout=15)
        err = (p.stderr or b"").decode("utf-8", "replace").strip()
        out = (p.stdout or b"").decode("utf-8", "replace").strip()
        if out:
            print("   stdout:", out[:500])
        if err:
            print("   stderr:", err[:800])
        if not out and not err:
            print("   无输出（可能窗口已正常创建）")
    except subprocess.TimeoutExpired:
        print("   诊断超时（窗口可能在等待 GUI 事件循环，属正常）")
    except Exception as exc:
        print("   诊断失败: %r" % (exc,))


def main(argv=None):
    ap = argparse.ArgumentParser(description="双窗启动器（逐个拉起并校验）")
    ap.add_argument("--ports", type=int, nargs="+", default=list(DEFAULT_PORTS))
    ap.add_argument("--views", nargs="+", default=list(DEFAULT_VIEWS))
    args = ap.parse_args(argv)

    print("=" * 62)
    print("双窗监视器启动器")
    print("=" * 62)

    pyw = find_pythonw()
    if not pyw:
        print("[FAIL] 找不到 python（试过：）")
        for p in PYW_CANDIDATES:
            print("   ", p)
        return 1
    print("解释器:", pyw)
    print("工作目录:", PROJ)
    print()

    results = []
    for i, (port, view) in enumerate(zip(args.ports, args.views), 1):
        title = "%s (%s)" % ("ABC"[i - 1], view)
        already = port_in_use(port)
        if already:
            print("[%s] 端口 %d 已被占用，跳过（可能已有同名窗口在跑）" % (title, port))
            results.append((title, port, "已占用", True))
            continue

        print("[%s] 拉起 port=%d view=%s ..." % (title, port, view))
        ok, detail = launch(pyw, port, view, title)
        print("   %s %s" % ("[OK]" if ok else "[FAIL]", detail))
        if not ok:
            diagnose(pyw, port, view)
        results.append((title, port, detail, ok))
        # 两个之间留点间隔，避免创建竞态
        time.sleep(1.0)

    print()
    print("=" * 62)
    okn = sum(1 for r in results if r[3])
    print("结果: %d/%d 窗口就绪" % (okn, len(results)))
    for title, port, detail, ok in results:
        print("  %-12s port=%-6d %s  %s"
              % (title, port, "[OK]  " if ok else "[FAIL]", detail))
    print("=" * 62)

    if okn == len(results):
        print()
        print("两个窗口都已就绪。测试命令记得各带端口：")
        print("  cli ... --port <口A> --mirror-port %d" % args.ports[0])
        print("  cli ... --port <口B> --mirror-port %d" % args.ports[1])
    return 0 if okn == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
