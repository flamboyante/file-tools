# -*- coding: utf-8 -*-
"""
draft_t_judges.py —— 给 T 段（标准快遥 / 标准慢遥51H）生成判据**草稿**并填入合并表。

规则（基于实测事实，不是拍脑袋）：
    快遥（值本身是中文）：
        备注同时含正面词+负面词（如「1：正常：0：异常」）→ 文本判据
        备注是纯模式/配置枚举（无好坏）               → 无需判据（模式类）
        备注为空、值恒定                             → 无需判据（恒定值）
        其余                                        → 待定
    慢遥（值是数值）：
        字段名含负面计数词（丢包/错误/失败/异常/失锁/断链/复位/跳变）→ 非零告警
        字段名 = 时间码                              → 无需判据（时间戳）
        备注含「单位」（模拟量）                       → 待定（附 0914 实测范围供参考）
        备注有正反对照                                → 枚举判据（按备注映射）
        字段名含「计数」（普通收发/请求计数）            → 无需判据（趋势观察）
        值恒定                                      → 无需判据（恒定值）
        其余                                        → 待定（附实测范围）

★ 生成的是**草稿**，落表后由小K逐条确认/修改；确认过的判据列就是正式判据来源。
"""

from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from openpyxl import load_workbook  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(os.path.dirname(HERE), "spec", "spec_merged_20260914.xlsx")

SHEET_FAST = "标准快遥"
SHEET_SLOW = "标准慢遥51H"
JUDGE_COL = 4          # T 段表原有 3 列，判据列加在第 4 列
JUDGE_HEADER = "判据"

POS = ("正常", "成功", "有效", "可用", "完成", "上电", "使能")
NEG = ("异常", "失败", "故障", "过高", "过低", "错误", "无效",
       "未接入", "中断", "损坏", "告警", "失锁", "过功率")
NEG_COUNT = ("丢包", "错误", "失败", "异常", "失锁", "断链", "复位", "跳变", "丢")


def load_t_text(csv_path: str):
    """读 CSV，返回 (表头, 每行的 T 段文本列表)。"""
    import csv
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    header = rows[0]
    t_idx = [i for i, n in enumerate(header) if n.startswith("TMXZJDT")]
    texts = [[r[i] for i in t_idx] for r in rows[1:]]
    return [header[i] for i in t_idx], texts


def numeric(series):
    """把一列文本里能转成数字的挑出来。"""
    out = []
    for v in series:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def suggest_fast(name: str, note: str, values: List[str]) -> str:
    has_pos = any(w in note for w in POS)
    has_neg = any(w in note for w in NEG)
    if has_pos and has_neg:
        return "文本判据：值含「异常/失败/错误」→告警；含「正常/成功」→通过"
    if note:
        return "无需判据（模式/配置类，取值无好坏）"
    if values and len(set(values)) == 1:
        return "无需判据（0914 恒定 {}）".format(values[0])
    return "待定"


def suggest_slow(name: str, note: str, values: List[str]) -> str:
    if "时间码" in name:
        return "无需判据（时间戳）"
    if any(w in name for w in NEG_COUNT):
        return "非零告警（0=通过）"
    if any(w in note for w in POS) and any(w in note for w in NEG):
        return "枚举判据（按备注映射：命中负面词=告警，命中正面词=通过）"
    nums = numeric(values)
    if "单位" in note and nums:
        return "待定（需阈值；0914 实测 {}~{}）".format(min(nums), max(nums))
    if "计数" in name:
        return "无需判据（趋势观察类）"
    if nums and len(set(nums)) == 1:
        return "无需判据（0914 恒定 {}）".format(int(nums[0]))
    if nums:
        return "待定（0914 实测 {}~{}）".format(min(nums), max(nums))
    return "待定"


def main() -> None:
    fast_hdr, fast_texts = load_t_text(r"V:\MY\PYQT\_extract\快遥-0914-00.csv")
    slow_hdr, slow_texts = load_t_text(r"V:\MY\PYQT\_extract\慢遥1-0914-00.csv")

    workbook = load_workbook(SPEC)
    stats = {}

    for sheet_name, header, texts, suggest in (
        (SHEET_FAST, fast_hdr, fast_texts, suggest_fast),
        (SHEET_SLOW, slow_hdr, slow_texts, suggest_slow),
    ):
        ws = workbook[sheet_name]
        ws.cell(row=1, column=JUDGE_COL, value=JUDGE_HEADER).font = ws.cell(row=1, column=1).font.copy()

        count = 0
        kinds: Dict[str, int] = {}
        for row_no in range(2, ws.max_row + 1):
            name = str(ws.cell(row=row_no, column=1).value or "").strip()
            if not name:
                continue
            col_values = [t[count] for t in texts if count < len(t)]
            note = str(ws.cell(row=row_no, column=3).value or "").strip()
            advice = suggest(name, note, col_values)
            ws.cell(row=row_no, column=JUDGE_COL, value="[草稿] " + advice)
            kind = advice.split("（")[0].split("：")[0]
            kinds[kind] = kinds.get(kind, 0) + 1
            count += 1
        stats[sheet_name] = (count, kinds)

    workbook.save(SPEC)

    for sheet_name, (count, kinds) in stats.items():
        print("[{}] 共 {} 列，草稿分布：{}".format(
            sheet_name, count, "、".join("{}={}".format(k, v) for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]))))

    # 打印全部草稿供审阅
    wb2 = load_workbook(SPEC, read_only=True, data_only=True)
    for sheet_name in (SHEET_FAST, SHEET_SLOW):
        ws = wb2[sheet_name]
        print()
        print("=" * 96)
        print("[{}] 判据草稿".format(sheet_name))
        print("=" * 96)
        for row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            name = str(row[0]).strip() if row[0] else ""
            note = str(row[2]).strip() if len(row) > 2 and row[2] else ""
            judge = str(row[3]).strip() if len(row) > 3 and row[3] else ""
            if not name:
                continue
            print("  {:>3}. {:<32} → {}".format(row_no - 1, name[:32], judge))


if __name__ == "__main__":
    main()
