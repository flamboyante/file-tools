# -*- coding: utf-8 -*-
"""
normalize_judges.py —— 把判据列里的各种手写写法，统一成 6 种标准格式。

标准格式（解析器只认这 6 种，见模块尾部的说明）：
    正常值:3            值等于 3 即通过，其他告警（单值/多值/枚举/精确/布尔统一归这类，多值用 | 分隔）
    正常范围:10~35      值落在区间内即通过，出界告警
    文本:异常|失败       值里含这些词即告警（值本身是中文结论的字段用，如快遥 T 段）
    结构对应:帧序号=0    该消息必须出现在帧序号=0 的包里（BMU 消息与帧序号强绑定）
    无需判据            明确不判（括号里的原因保留）
    待定(说明)          还没定（括号里保留实测范围等参考信息）

原则：**只改格式，不改语义**。每一条的转换对照都会打印出来供核对；
      解析不了的标 !!未识别，由人工处理。
"""

from __future__ import annotations

import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from openpyxl import load_workbook  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(os.path.dirname(HERE), "spec", "spec_merged_20260914.xlsx")

# (sheet 名, 判据列号 1-based, 备注列号 1-based)
TARGETS = [
    ("通道0（slot0）", 14, 13),
    ("通道2（slot3）", 14, 13),
    ("通道3（slot5）", 14, 13),
    ("标准快遥", 4, 3),
    ("标准慢遥51H", 4, 3),
]

POS = ("正常", "成功", "有效", "可用", "完成", "上电", "使能")
NEG = ("异常", "失败", "故障", "过高", "过低", "错误", "无效",
       "未接入", "中断", "损坏", "告警", "失锁", "过功率")


def normalize(raw: str, note: str) -> str:
    """把一条手写判据转成标准格式。返回标准化文本；解析不了返回带 !! 标记的原文。"""
    text = (raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\[草稿\]\s*", "", text)          # 去掉草稿前缀
    text = re.sub(r"^!!未识别[:：]?\s*", "", text)     # 上一轮未识别的，这轮重试
    text = text.replace("慢摇帧序号", "帧序号").replace("慢遥帧序号", "帧序号")

    # ★ 幂等：已经是标准格式的，原样返回（脚本可以反复跑）
    if re.match(r"^(正常值:|正常范围:|文本:|结构对应:|总体:|无需判据|待定)", text):
        return text

    # ---- 无需判据 ----
    if text.startswith("无需判据"):
        tail = re.search(r"[（(]([^）)]*)[）)]\s*$", text)
        return "无需判据" + ("({})".format(tail.group(1)) if tail else "")

    # ---- 待定 ----
    if text.startswith("待定"):
        tail = re.search(r"[（(]([^）)]*)[）)]\s*$", text)
        inner = re.sub(r"\s+", "", tail.group(1)) if tail else ""
        return "待定" + ("({})".format(inner) if inner else "")

    # ---- 新增类型：跨拍判据（小K 09-15 补充）----
    if "每次都有变化" in text:
        return "总体:有变化"                 # 值应随拍变化，不变=异常（如时间码/请求计数）
    if "历史记录" in text or "历史" in text:
        return "总体:按历史基线"              # 以历史常见值为基线，偏离=异常（CPU/SOC 状态类）

    # ---- 「按这个先来」：以 0914 实测范围作初始阈值（小K 授权）----
    m = re.search(r"按这个先来.*?实测\s*([\d.]+)\s*~\s*([\d.]+)", text)
    if m:
        return "正常范围:{}~{}".format(m.group(1), m.group(2))

    # ---- 结构对应 ----
    m = re.search(r"和?帧序号为?(\d)强对应", text)
    if m:
        return "结构对应:帧序号={}".format(m.group(1))

    # ---- 正常范围 ----
    m = re.search(r"正常是?大于\s*(\d+)\s*小于\s*(\d+)", text)
    if m:
        return "正常范围:{}~{}".format(m.group(1), m.group(2))

    # ---- 正常值（各种写法统一，兼容「正常是」和「正常为」）----
    # 「正常是3或者4，其他异常」
    m = re.search(r"正常[是为](\d+)\s*或者\s*(\d+)", text)
    if m:
        return "正常值:{}|{}".format(m.group(1), m.group(2))
    # 「正常为：00：正常，异常为其他」
    m = re.search(r"正常[是为][:：]?\s*(\d+)\s*[:：]\s*正常", text)
    if m:
        return "正常值:{}".format(int(m.group(1)))
    # 「正常是0和1，其他异常」
    m = re.search(r"正常[是为](\d+)\s*和\s*(\d+)", text)
    if m:
        return "正常值:{}|{}".format(m.group(1), m.group(2))
    # 「正常为1，异常为0」（布尔）
    m = re.search(r"正常[是为](\d+)\s*[，,]\s*异常为(\d+)", text)
    if m:
        return "正常值:{}".format(m.group(1))
    # 「正常为0，非0告警」
    m = re.search(r"正常[是为](\d+)[，,]?\s*非\d*告警", text)
    if m:
        return "正常值:{}".format(m.group(1))
    # 「非零报告警」≡ 0 为正常
    if "非零" in text and "告警" in text:
        return "正常值:0"
    # 「非FF报告警」≡ FF 为正常
    m = re.search(r"非([0-9A-Fa-f]{1,8})报告警", text)
    if m:
        return "正常值:{}".format(m.group(1).upper())
    # 「正常为正常，其他均为异常」→ 值本身就是中文结论，按文本判
    if re.search(r"正常[是为]正常", text):
        return "文本:异常|失败|故障|过高|过低"
    # 「正常为0x7FFFFF，异常为其他」/「正常是3，其他异常」
    m = re.search(r"正常[是为][:：]?\s*([0-9][0-9A-Fa-fxX]*)", text)
    if m and ("异常" in text or "其他" in text):
        return "正常值:{}".format(m.group(1))

    # ---- 文本（T 段：值本身是中文结论）----
    m = re.search(r"值含[「『]([^」』]+)[」』]", text)
    if m:
        return "文本:{}".format(m.group(1).replace("／", "|"))
    if text.startswith("文本:"):
        return text

    # ---- 枚举（按备注映射，提取"含义为正面"的值）----
    if "枚举" in text or "按备注" in text:
        vals = []
        for mm in re.finditer(r"([0-9]+|[0b][01]+)\s*[:：]\s*([^;；/，,\n]+)", note or ""):
            meaning = mm.group(2)
            if any(w in meaning for w in POS) and not any(w in meaning for w in NEG):
                vals.append(mm.group(1))
        if vals:
            return "正常值:{}".format("|".join(vals))
        return "!!未识别(枚举但备注提取不到正常值): " + raw

    return "!!未识别: " + raw


def main() -> None:
    workbook = load_workbook(SPEC)
    changes: List = []
    unidentified: List = []
    stats: Dict = {}

    for sheet_name, judge_col, note_col in TARGETS:
        ws = workbook[sheet_name]
        for row_no in range(2, ws.max_row + 1):
            name = str(ws.cell(row=row_no, column=1).value or "").strip()
            raw = ws.cell(row=row_no, column=judge_col).value
            note = ws.cell(row=row_no, column=note_col).value
            raw_text = str(raw or "").strip()
            if not name and not raw_text:
                continue

            standard = normalize(raw_text, str(note or ""))
            key = standard.split("(")[0].split(":")[0]
            stats[key] = stats.get(key, 0) + 1

            if standard != raw_text:
                changes.append((sheet_name, row_no, name, raw_text, standard))
            if standard.startswith("!!"):
                unidentified.append((sheet_name, row_no, name, raw_text))
            ws.cell(row=row_no, column=judge_col, value=standard)

    workbook.save(SPEC)

    print("=== 标准化统计 ===")
    for key, count in sorted(stats.items(), key=lambda kv: -kv[1]):
        print("  {:<14} {} 条".format(key, count))

    print("\n=== !! 未识别（需人工处理）{} 条 ===".format(len(unidentified)))
    for sheet_name, row_no, name, raw in unidentified:
        print("  {} 第{}行 {}: {}".format(sheet_name, row_no, name, raw))

    print("\n=== 格式被改动的条目 {} 条（原文 → 标准化）===".format(len(changes)))
    for sheet_name, row_no, name, raw, standard in changes:
        if standard.startswith("!!"):
            continue
        print("  {} 行{:<4} {:<28} | {}  ⇒  {}".format(
            sheet_name[:4], row_no, name[:28], raw[:52], standard))


if __name__ == "__main__":
    from typing import Dict, List
    main()
