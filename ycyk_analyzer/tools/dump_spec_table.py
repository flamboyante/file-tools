# -*- coding: utf-8 -*-
"""
dump_spec_table.py —— 把解析表（标三-慢遥测试表）原样打印出来看。

为什么需要它：
    写正式解析代码之前，必须先亲眼确认表里的真实结构 ——
    sheet 叫什么、每页多少行、消息是怎么切分的、备注里 type/length 是怎么写的。
    只靠文档描述容易踩坑（例如把 channelId 看成了 TMXZJDZ2148）。

怎么用：
    python tools/dump_spec_table.py          # 列出所有 sheet 的名称
    python tools/dump_spec_table.py 1        # 打印第 1 个 sheet 的明细
    python tools/dump_spec_table.py 0 1 2 3  # 一次打印多个

说明：
    这是"看表"用的辅助脚本，不参与正式解析流程，删掉也不影响主程序。
"""

from __future__ import annotations  # 让 Python 3.8 也能用新式类型标注

import os
import sys

# Windows 控制台默认编码是 GBK，直接 print 中文有时会报 UnicodeEncodeError。
# 这里把标准输出强制改成 UTF-8，保证中文能正常显示。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from openpyxl import load_workbook  # noqa: E402  （放在编码设置之后导入更安全）


# 本文件在 ycyk_analyzer/tools/ 下，所以解析表在上两级目录的 spec/ 里
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_DIR = os.path.join(os.path.dirname(HERE), "spec")
SPEC_FILE = os.path.join(SPEC_DIR, "标三-慢遥测试表-20260512.xlsx")

# 18 列的列号（从 1 开始数），写在这里方便对照表头
COL = {
    "模块": 1,
    "序号": 2,
    "遥测代号": 3,
    "参数名称": 4,
    "数据类型": 5,
    "转换公式": 6,
    "转换后类型": 7,
    "上限": 8,
    "下限": 9,
    "期望值": 10,
    "单位": 11,
    "长度bit": 12,
    "备注": 13,
    "测试时间": 14,
    "研发支持": 15,
    "验证结果": 16,
    "总包长": 17,
    "2368": 18,
}


def text(value):
    """把单元格内容统一变成"去掉首尾空格的字符串"，空单元格返回空串。"""
    if value is None:
        return ""
    return str(value).strip()


def col(row, col_no):
    """从一行里取第 col_no 列（列号从 1 开始），越界就当空值处理。"""
    idx = col_no - 1
    if idx < 0 or idx >= len(row):
        return ""
    return text(row[idx])


def main():
    print("解析表:", SPEC_FILE)
    if not os.path.isfile(SPEC_FILE):
        print("!! 文件不存在，请检查路径")
        return

    # read_only=True 读得快；data_only=True 表示若单元格是公式，取它算好的值
    wb = load_workbook(SPEC_FILE, read_only=True, data_only=True)

    print("\nsheet 名单:")
    for i, name in enumerate(wb.sheetnames):
        ws = wb[name]
        print("  [{}] {}   ({} 行 x {} 列)".format(i, name, ws.max_row, ws.max_column))

    # 没带参数时只列名单，不打印明细
    if len(sys.argv) < 2:
        print("\n想细看某一页：python tools/dump_spec_table.py <上面的序号>")
        return

    for arg in sys.argv[1:]:
        idx = int(arg)
        name = wb.sheetnames[idx]
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))

        print("\n" + "=" * 100)
        print("sheet[{}] = {}   共 {} 行".format(idx, name, len(rows)))
        print("=" * 100)
        print(
            "行号 | {:<8} | {:<30} | {:>10} | {}".format(
                COL_NAME["模块"], COL_NAME["参数名称"], COL_NAME["长度bit"], COL_NAME["备注"]
            )
        )
        print("-" * 100)

        for line_no, row in enumerate(rows, start=1):
            print(
                "{:>4} | {:<8} | {:<30} | {:>10} | {}".format(
                    line_no,
                    col(row, COL["模块"])[:8],
                    col(row, COL["参数名称"])[:30],
                    col(row, COL["长度bit"])[:10],
                    col(row, COL["备注"]),
                )
            )


# 表头中文名，仅用于打印
COL_NAME = {"模块": "模块", "参数名称": "参数名称", "长度bit": "长度/bit", "备注": "备注"}


if __name__ == "__main__":
    main()
