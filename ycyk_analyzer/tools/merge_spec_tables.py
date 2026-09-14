# -*- coding: utf-8 -*-
"""
merge_spec_tables.py —— 把「slot 定义表」和「T 段定义表」合并成一份自包含的解析表。

为什么要合并：
    本来要依赖两张表 —— slot 定义在 `标三-慢遥测试表-20260512.xlsx`，
    T 段定义在 `PreCanDeal_T段_20260715.xlsx`。换机器 / 换人就容易缺文件。
    合并成一份后，本项目只依赖这一个 xlsx。

合并规则（**只搬运，不改任何数据**）：
    - slot 定义：取 `标三-慢遥测试表-20260512.xlsx` 的 4 个通道页（小K 确认这是最新版）
    - T 段定义：取 `PreCanDeal_T段_20260715.xlsx` 的 标准快遥 / 标准慢遥51H/52H/53H
    - **页名、列结构一律保持原样** —— 这样解析代码不用改，也能与源表逐格对账

用法：
    python tools/merge_spec_tables.py

输出：
    spec/spec_merged_20260914.xlsx   （第一页「说明」记录了来源与校验结果）
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime

# Windows 控制台默认 GBK，强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.dirname(HERE)          # ycyk_analyzer/
SPEC_DIR = os.path.join(PKG_DIR, "spec")
sys.path.insert(0, PKG_DIR)

from spec import EXPECTED_TOTAL_BITS, parse_sheet  # noqa: E402

# --- 输入 ---
SLOT_SRC = os.path.join(SPEC_DIR, "标三-慢遥测试表-20260512.xlsx")
T_SRC = os.path.join(SPEC_DIR, "PreCanDeal_T段_20260715.xlsx")

# --- 输出 ---
OUT = os.path.join(SPEC_DIR, "spec_merged_20260914.xlsx")

# --- 要搬哪些页（顺序也按这个来）---
SLOT_SHEETS = ["通道0（slot0）", "通道1（slot2）", "通道2（slot3）", "通道3（slot5）"]
T_SHEETS = ["标准快遥", "标准慢遥51H", "标准慢遥52H", "标准慢遥53H"]

# ⚠️ 本脚本是「整体重写」合并表 —— 源表更新时才需要重跑。
# 若已经在 spec_merged_*.xlsx 上做过手工修正，重跑会覆盖掉，需要重新应用一遍。
# 已知的 1 处手工修正：通道2（slot3）里 1051 的备注 length=18字节 → 17字节
# （依据：字段位长合计 = 21 字节 = 4+17，且实测所有 slot3 包里该消息头写的就是 17）。


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def file_md5(path: str) -> str:
    """算文件 md5，用来记录"这份合并表是从哪个版本搬来的"。"""
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def display_width(text: str) -> int:
    """估算一行字在 Excel 里占多宽（中文按 2 个字符宽算）。"""
    width = 0
    for ch in text:
        width += 2 if ord(ch) > 0x2E80 else 1
    return width


def copy_sheet(src_ws, dst_wb, title: str):
    """把源表的一页，原样复制到新工作簿（值 + 表头加粗 + 列宽 + 自动换行 + 冻结首行）。"""
    dst = dst_wb.create_sheet(title=title)
    rows = list(src_ws.iter_rows(values_only=True))

    for r_idx, row in enumerate(rows, start=1):
        for c_idx, value in enumerate(row, start=1):
            if value is None:
                continue
            dst.cell(row=r_idx, column=c_idx, value=value)

    col_count = max((len(r) for r in rows), default=0)

    # 表头加粗
    for c_idx in range(1, col_count + 1):
        cell = dst.cell(row=1, column=c_idx)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    # 列宽：取该列最长内容的宽度，限制在 8~60 之间
    for c_idx in range(1, col_count + 1):
        widest = 0
        for row in rows:
            if c_idx - 1 >= len(row) or row[c_idx - 1] is None:
                continue
            for line in str(row[c_idx - 1]).splitlines() or [""]:
                widest = max(widest, display_width(line))
        dst.column_dimensions[get_column_letter(c_idx)].width = min(max(widest + 2, 8), 60)

    # 正文统一「顶端对齐 + 自动换行」，长备注才不会撑成一条线
    for r_idx in range(2, len(rows) + 1):
        for c_idx in range(1, col_count + 1):
            dst.cell(row=r_idx, column=c_idx).alignment = Alignment(
                vertical="top", wrap_text=True
            )

    dst.freeze_panes = "A2"  # 冻结首行，滚动时表头不跑
    return len(rows), col_count


def build_note_sheet(dst_wb, slot_info: list, t_info: list, verify_lines: list):
    """第一页「说明」：记录来源、校验结果、以及用这张表时必须知道的几件事。"""
    ws = dst_wb.create_sheet(title="说明", index=0)

    lines = [
        ["合并解析表（slot 定义 + T 段定义）"],
        [],
        ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["生成脚本", "ycyk_analyzer/tools/merge_spec_tables.py"],
        [],
        ["— 来源一：slot 定义（最新权威版本）—"],
        ["源文件", os.path.basename(SLOT_SRC)],
        ["源文件 md5", file_md5(SLOT_SRC)],
        ["搬运的页", "、".join(SLOT_SHEETS)],
        [],
        ["— 来源二：T 段定义（内容长期未变）—"],
        ["源文件", os.path.basename(T_SRC)],
        ["源文件 md5", file_md5(T_SRC)],
        ["搬运的页", "、".join(T_SHEETS)],
        ["注意", "源文件里另有「慢遥1_通道*_slot*」4 页，那是旧版 slot 定义，本表未采用"],
        [],
        ["— 搬运后的校验结果 —"],
    ]
    lines += verify_lines

    lines += [
        [],
        ["— 用这张表时必须知道的几件事 —"],
        ["1", "消息切分规则：参数名称里含「消息ID」的行 = 一条新消息的开始"],
        [
            "2",
            "消息ID 有三种写法，type 位置不固定："
            "「消息ID（type=1000）」type 在名称里；"
            "裸「消息ID」的 type 写在备注里（如 type=1010）；"
            "「BMU消息ID(t=1050)」用的是 t= 不是 type=",
        ],
        ["3", "一条消息可能对应两个 type，按制式分，例如备注写的 type=1200(sc),1201(ka)"],
        [
            "4",
            "消息之间夹着「预留 / 保留 / 慢遥帧序号」，它们不属于消息内容；"
            "拆开后每条消息的「业务字段+消息头」才等于备注声明的 length",
        ],
        ["5", "备注里的 length=NN字节 是载荷长度（不含 4 字节消息头），所以消息总长 = (NN+4)×8 bit"],
        [
            "6",
            "T 段表的第 3 列列名叫「转换公式」，但实际内容是枚举说明与判据"
            "（例如 0000：正常; 1111：异常）—— 不能因为列名是公式就忽略它",
        ],
        ["7", "每页末尾的校验行（参数名称为空、长度bit = 1184）= 一个 slot 包的载荷总位长，可作自检"],
        [],
        ["— V1 判据范围（其他字段一律「暂不判据」）—"],
        ["", "BMU 的 1050 / 1051 / 1052，加上快遥 T 段、慢遥 51H T 段"],
        ["", "慢遥 52H / 53H 已一并搬入本表备查，但 V1 暂不使用"],
    ]

    for r_idx, row in enumerate(lines, start=1):
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    ws.cell(row=1, column=1).font = Font(bold=True, size=13)
    for r_idx, row in enumerate(lines, start=1):
        if row and str(row[0]).startswith("—"):
            ws.cell(row=r_idx, column=1).font = Font(bold=True)

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 96


def main():
    for path in (SLOT_SRC, T_SRC):
        if not os.path.isfile(path):
            print("!! 缺源文件：" + path)
            return

    wb_slot = load_workbook(SLOT_SRC, read_only=True, data_only=True)
    wb_t = load_workbook(T_SRC, read_only=True, data_only=True)
    wb_out = Workbook()
    wb_out.remove(wb_out.active)  # 去掉默认的空页，后面自己建

    slot_info = []
    print("=== 搬运 slot 定义 ===")
    for name in SLOT_SHEETS:
        if name not in wb_slot.sheetnames:
            print("  !! 源表里没有这一页：" + name)
            return
        n_rows, n_cols = copy_sheet(wb_slot[name], wb_out, name)
        slot_info.append((name, n_rows, n_cols))
        print("  {}   {} 行 x {} 列".format(name, n_rows, n_cols))

    t_info = []
    print("=== 搬运 T 段定义 ===")
    for name in T_SHEETS:
        if name not in wb_t.sheetnames:
            print("  !! 源表里没有这一页：" + name)
            return
        n_rows, n_cols = copy_sheet(wb_t[name], wb_out, name)
        t_info.append((name, n_rows, n_cols))
        print("  {}   {} 行 x {} 列".format(name, n_rows, n_cols))

    wb_out.save(OUT)
    print("\n已写出：" + OUT)

    # ---------------- 搬完立刻校验：读回来，用 spec.py 的逻辑自检 ----------------
    print("\n=== 校验（读回新表，检查结构自检的位长）===")
    verify_lines = []
    wb_check = load_workbook(OUT, read_only=True, data_only=True)

    all_ok = True
    for name in SLOT_SHEETS:
        rows = list(wb_check[name].iter_rows(values_only=True))
        slot = parse_sheet(rows, name)
        ok = slot.check_ok
        all_ok = all_ok and ok
        line = "{}：字段合计 {} / 页末校验 {} → {}".format(
            name, slot.total_bits, slot.declared_total_bits, "通过" if ok else "不一致"
        )
        print("  " + line)
        verify_lines.append(["", line])

    for name, n_rows, n_cols in t_info:
        verify_lines.append(["", "{}：{} 行 x {} 列".format(name, n_rows, n_cols)])

    verify_lines.insert(0, ["每页位长必须 = {}".format(EXPECTED_TOTAL_BITS), "读回校验结果："])

    # 生成「说明」页（带来源 md5、校验结果、使用要点），放第一页，再存一次
    build_note_sheet(wb_out, slot_info, t_info, verify_lines)
    wb_out.save(OUT)

    print("\n总判定：" + ("全部通过" if all_ok else "存在不一致"))
    print("说明页已带上来源 md5 与校验结果：" + OUT)


if __name__ == "__main__":
    main()
