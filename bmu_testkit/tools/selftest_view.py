# -*- coding: utf-8 -*-
"""ASCII/HEX 双视图渲染自测（无需 GUI、无需硬件）。

直接从 watch_serial.py 源码里提取 `_render_body` 执行，
保证测的是真实代码而不是副本 —— 避免"测试通过但程序里还是错的"。

    D:\\Anaconda3\\envs\\pyqt_side_all_0328\\python.exe bmu_testkit\\tools\\selftest_view.py
"""

from __future__ import print_function

import io
import os
import re
import sys

if sys.version_info[0] >= 3:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "watch_serial.py")


def load_render_body():
    """从源码抠出 _render_body 方法体，注入一个最小替身类。"""
    with open(SRC, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"    def _render_body.*?(?=\n    def )", src, re.S)
    if not m:
        raise RuntimeError("在 watch_serial.py 里找不到 _render_body")
    # 源码里是 \n 字面量，exec 前还原成真实换行
    body = m.group(0).replace("\\n", "\n")
    ns = {}
    stub = ("class Stub(object):\n"
            "    def __init__(self, view):\n"
            "        self.view = view\n"
            + body)
    exec(compile(stub, "<extracted>", "exec"), ns)
    return ns["Stub"]


CASES = [
    (b"[BL] boot ok\r\n",                 "CRLF 日志"),
    (b"[APP] ver=3.3.0\r\n",              "带版本号"),
    (b"\x00\x01\x02\xff\xfe",             "全不可打印"),
    (b"\x1a\xcf\x00\x18\xc0\x03\x00\x01",  "422 二进制帧"),
    (b"col1\tcol2\r\n",                   "TAB 保留"),
    (b"hello world",                      "纯 ASCII 无换行"),
    (b"",                                  "空载荷"),
]

CHECKS = [
    # (描述, view, 输入, 期望输出)
    ("0xFF 必须显示为点",      "ascii", b"\xff", ".", ),
    ("0xCF 必须显示为点",      "ascii", b"\xcf", "."),
    ("可打印字符原样保留",      "ascii", b"ABC", "ABC"),
    ("TAB 保留",              "ascii", b"a\tb", "a\tb"),
    ("CR 变点(不产生空行)",     "ascii", b"a\r\nb", "a..b"),
    ("hex 视图方向正确",        "hex",   b"\x1a\xcf", "1a cf"),
    ("hex 视图空载荷",          "hex",   b"", ""),
]


def main():
    Stub = load_render_body()

    print("=" * 92)
    print("%-18s | %-34s | %s" % ("场景", "hex", "ascii"))
    print("-" * 92)
    for data, desc in CASES:
        print("%-18s | %-34s | %r"
              % (desc, Stub("hex")._render_body(data),
                 Stub("ascii")._render_body(data)))
    print("-" * 92)

    failed = 0
    for desc, view, data, want in CHECKS:
        got = Stub(view)._render_body(data)
        ok = got == want
        if not ok:
            failed += 1
        print("%s  %-24s view=%-5s  got=%r want=%r"
              % ("PASS" if ok else "FAIL", desc, view, got, want))

    print("=" * 92)
    total = len(CHECKS)
    print("结果: %d/%d 通过" % (total - failed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
