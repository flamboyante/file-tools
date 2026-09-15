# -*- coding: utf-8 -*-
"""
report.py —— 出一份带判据着色的 xlsx（V1 阶段1：最简单最基础的判据）。

**判据不在本文件里** —— 全部来自 `rules.csv`（见 `rules.py`）：
    规则支持三种范围：**瞬时**（逐拍判，用于明细着色）／**总体**（跨拍统计后判）／**两者**。
    → **加判据 = 在 rules.csv 里加一行，不用改代码。**

输出结构（快遥 + 慢遥合成**一份**表）：
    告警汇总-快遥 / 告警汇总-慢遥     按字段聚合，一行一个异常点
    告警明细-快遥 / 告警明细-慢遥     逐拍明细
    T段-快遥 / T段-慢遥                T 段原始值（每包一行）
    slot0 / slot3 / slot5             慢遥各通道的 BMU 字段

用法：
    python report.py <csv>                       单个文件 → 同名 _判据.xlsx
    python report.py <快遥csv> <慢遥csv> <输出xlsx>   两路合成一份（顺序任意）
"""

from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dataclasses import dataclass, field  # noqa: E402
from typing import Dict, List, Optional, Tuple  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from frame import SEQ_TO_SLOT, decode_frame, load_slots_by_seq  # noqa: E402
from rules import load_rules  # noqa: E402
from t_segment import load_t_segments, pick_segment  # noqa: E402
from table_csv import load_csv  # noqa: E402

# ---------------------------------------------------------------------------
# 三态与配色（红=告警，绿=通过，无色=暂不判据）
# ---------------------------------------------------------------------------

OK = "通过"
ALARM = "告警"
NA = "暂不判据"

FILL_OK = PatternFill("solid", fgColor="EAF3DE")
FILL_ALARM = PatternFill("solid", fgColor="FCEBEB")
FONT_OK = Font(color="27500A", size=10)
FONT_ALARM = Font(color="A32D2D", bold=True, size=10)
FONT_HEAD = Font(bold=True, size=10)
ALIGN_WRAP = Alignment(vertical="top", wrap_text=True)

# ---------------------------------------------------------------------------
# 判据：全部来自 rules.csv（见 rules.py）—— 加判据只需在 Excel 里加一行
# ---------------------------------------------------------------------------

RULESET = load_rules()


def judge_field(name: str, value, note: str = "") -> str:
    """瞬时判据（逐拍）。规则写在 rules.csv，代码里不硬编码。"""
    return RULESET.judge(name, value, note)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class AlarmItem:
    """一条告警记录，用于告警汇总 / 告警明细。"""

    source: str
    row_no: int
    time: str
    field_name: str
    value: str
    verdict: str
    note: str = ""
    total_rows: int = 0     # 该数据块一共多少拍（算"总体结论"的比例要用）


@dataclass
class SheetData:
    """要写进 xlsx 的一张表。"""

    title: str
    headers: List[str] = field(default_factory=list)
    rows: List[List[object]] = field(default_factory=list)
    verdicts: List[List[str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 组装表数据
# ---------------------------------------------------------------------------


def build_t_sheet(csv_data, segment, title: str) -> SheetData:
    """T 段 → 一张表（每包一行）。"""
    sheet = SheetData(title=title)
    sheet.headers = ["时间"] + [f.name for f in segment.fields]
    sheet.notes = [""] + [f.note for f in segment.fields]

    for row in csv_data.rows:
        values = segment.with_values(row.t_text)
        data_row: List[object] = [row.dm_time]
        verdict_row = [""]
        for fld in values:
            data_row.append(fld.raw)
            verdict_row.append(judge_field(fld.name, fld.raw, fld.note))
        sheet.rows.append(data_row)
        sheet.verdicts.append(verdict_row)
    return sheet


def build_bmu_sheet(slot, frames) -> Optional[SheetData]:
    """某个 slot 的 BMU 字段 → slotN 页。该通道没有 BMU 时返回 None。"""
    bmu_msgs = [m for m in slot.messages if m.type_ids and m.type_ids[0] in ("1050", "1051", "1052")]
    if not bmu_msgs:
        return None
    msg = bmu_msgs[0]
    bmu_fields = [f for f in msg.fields if f.role == "field"]
    if not bmu_fields:
        return None

    sheet = SheetData(title="slot{}".format(slot.slot_no))
    sheet.headers = ["时间", "type"] + [f.name for f in bmu_fields]
    sheet.notes = ["", ""] + [f.note for f in bmu_fields]

    for frame, dm_time in frames:
        decoded = None
        for m in frame.messages:
            if m.type_id in ("1050", "1051", "1052"):
                decoded = m
                break
        if decoded is None:
            continue
        row: List[object] = [dm_time, decoded.label]
        verdict_row = ["", ""]
        by_name = {f.name: f for f in decoded.business_fields}
        for spec_field in bmu_fields:
            got = by_name.get(spec_field.name)
            if got is None:
                row.append("")
                verdict_row.append(NA)
            else:
                row.append(got.value)
                verdict_row.append(judge_field(spec_field.name, got.value, spec_field.note))
        sheet.rows.append(row)
        sheet.verdicts.append(verdict_row)
    return sheet


def collect_alarms(sheet: SheetData) -> List[AlarmItem]:
    """把一张表里判定为"告警"的单元格收集起来。"""
    out: List[AlarmItem] = []
    for r_idx, verdict_row in enumerate(sheet.verdicts):
        for c_idx, verdict in enumerate(verdict_row):
            if verdict == ALARM:
                out.append(AlarmItem(
                    source=sheet.title,
                    row_no=r_idx + 1,
                    time=sheet.rows[r_idx][0],
                    field_name=sheet.headers[c_idx],
                    value=str(sheet.rows[r_idx][c_idx]),
                    verdict=verdict,
                    note=sheet.notes[c_idx],
                    total_rows=len(sheet.rows),
                ))
    return out


def analyze_one(csv_path: str, t_segments, spec_map) -> Dict:
    """解析一个文件（快遥或慢遥），返回它的表与告警。"""
    data = load_csv(csv_path)
    kind = "慢遥" if data.is_slot_data else "快遥"
    entry: Dict = {"path": csv_path, "kind": kind, "data": data, "workloads": [], "alarms": []}

    # T 段
    segment = pick_segment(t_segments, data.t_columns)
    if segment is not None:
        sheet = build_t_sheet(data, segment, "T段-{}".format(kind))
        entry["workloads"].append(sheet)
        entry["alarms"].extend(collect_alarms(sheet))

    # BMU（只有慢遥有 Z 段）
    if data.is_slot_data:
        frames_by_slot: Dict[int, List[Tuple[object, str]]] = {}
        for row in data.rows:
            slot_no = SEQ_TO_SLOT.get(row.z_bytes[147])
            if slot_no is None or slot_no not in spec_map:
                continue
            frame = decode_frame(bytes(row.z_bytes), spec_map[slot_no], row.row_no)
            frames_by_slot.setdefault(slot_no, []).append((frame, row.dm_time))
        for slot_no in sorted(frames_by_slot):
            bmu_sheet = build_bmu_sheet(spec_map[slot_no], frames_by_slot[slot_no])
            if bmu_sheet is None:
                continue
            entry["workloads"].append(bmu_sheet)
            entry["alarms"].extend(collect_alarms(bmu_sheet))

    return entry


# ---------------------------------------------------------------------------
# 写 xlsx
# ---------------------------------------------------------------------------


def write_sheet(workbook, sheet: SheetData) -> None:
    ws = workbook.create_sheet(title=sheet.title)
    ws.append(sheet.headers)
    for idx in range(1, len(sheet.headers) + 1):
        ws.cell(row=1, column=idx).font = FONT_HEAD
        ws.cell(row=1, column=idx).alignment = ALIGN_WRAP
    ws.freeze_panes = "B2"

    for r_idx, data_row in enumerate(sheet.rows, start=2):
        verdict_row = sheet.verdicts[r_idx - 2]
        for c_idx, value in enumerate(data_row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.alignment = ALIGN_WRAP
            verdict = verdict_row[c_idx - 1] if c_idx - 1 < len(verdict_row) else ""
            if verdict == ALARM:
                cell.fill = FILL_ALARM
                cell.font = FONT_ALARM
            elif verdict == OK:
                cell.fill = FILL_OK
                cell.font = FONT_OK

    for c_idx, head in enumerate(sheet.headers, start=1):
        widest = len(str(head))
        for data_row in sheet.rows[:80]:
            if c_idx - 1 < len(data_row):
                widest = max(widest, min(len(str(data_row[c_idx - 1])), 40))
        ws.column_dimensions[get_column_letter(c_idx)].width = min(max(widest + 3, 9), 34)


def _flat(text: str, limit: int = 200) -> str:
    return " ".join((text or "").splitlines())[:limit]


def write_alarm_sheets(workbook, alarms: List[AlarmItem], kind: str, source_name: str, index: int) -> None:
    """写一对页：**告警汇总-KIND**（按字段聚合）+ **告警明细-KIND**（逐拍）。"""
    order: List[Tuple[str, str]] = []
    agg: Dict[Tuple[str, str], Dict[str, object]] = {}
    for item in alarms:
        key = (item.source, item.field_name)
        if key not in agg:
            agg[key] = {"count": 0, "first": item.time, "last": item.time,
                        "value": item.value, "note": item.note, "total": item.total_rows}
            order.append(key)
        agg[key]["count"] = int(agg[key]["count"]) + 1
        agg[key]["last"] = item.time

    ws = workbook.create_sheet(title="告警汇总-{}".format(kind), index=index)
    headers = ["数据块", "字段", "异常拍数", "总拍数", "总体结论", "首次时间", "末次时间", "值", "判据说明"]
    ws.append(headers)
    for idx in range(1, len(headers) + 1):
        ws.cell(row=1, column=idx).font = FONT_HEAD
        ws.cell(row=1, column=idx).alignment = ALIGN_WRAP
    ws.freeze_panes = "A2"

    for r_idx, key in enumerate(order, start=2):
        entry = agg[key]
        count = int(entry["count"])
        total = int(entry["total"])
        # ★ 总体结论：交给 rules.csv 里「判据范围 = 总体 / 两者」的规则
        summary = RULESET.summarize(key[1], total, count) or ""
        values = [key[0], key[1], count, total, summary,
                  entry["first"], entry["last"], entry["value"], _flat(str(entry["note"]))]
        for c_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.alignment = ALIGN_WRAP
            if c_idx == 2:
                cell.fill = FILL_ALARM
                cell.font = FONT_ALARM
            elif c_idx == 5 and summary:
                cell.font = FONT_ALARM
    for c_idx, width in enumerate([10, 30, 10, 8, 12, 22, 22, 12, 46], start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = width
    ws.cell(row=max(len(order) + 2, 4), column=1,
            value="来源：{}　（同一字段只在汇总里占一行；「总体结论」来自 rules.csv 的总体规则）".format(
                source_name)).font = Font(size=9, italic=True)

    ws2 = workbook.create_sheet(title="告警明细-{}".format(kind), index=index + 1)
    headers2 = ["数据块", "行号", "时间", "字段", "值", "判定", "判据说明"]
    ws2.append(headers2)
    for idx in range(1, len(headers2) + 1):
        ws2.cell(row=1, column=idx).font = FONT_HEAD
        ws2.cell(row=1, column=idx).alignment = ALIGN_WRAP
    ws2.freeze_panes = "A2"
    for r_idx, item in enumerate(alarms, start=2):
        values = [item.source, item.row_no, item.time, item.field_name, item.value,
                  item.verdict, _flat(item.note)]
        for c_idx, value in enumerate(values, start=1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=value)
            cell.alignment = ALIGN_WRAP
            if c_idx == 6:
                cell.fill = FILL_ALARM
                cell.font = FONT_ALARM
    for c_idx, width in enumerate([10, 8, 22, 30, 18, 10, 50], start=1):
        ws2.column_dimensions[get_column_letter(c_idx)].width = width


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def build_report(csv_paths: List[str], out_path: Optional[str] = None) -> str:
    """把 1~2 个 CSV（快遥 / 慢遥，顺序任意）解析成**一份** xlsx。"""
    t_segments = load_t_segments()
    spec_map = load_slots_by_seq()

    entries = [analyze_one(p, t_segments, spec_map) for p in csv_paths]

    workbook = Workbook()
    workbook.remove(workbook.active)

    # 告警页放最前：快、慢各一对
    index = 0
    for entry in entries:
        write_alarm_sheets(workbook, entry["alarms"], entry["kind"],
                           os.path.basename(entry["path"]), index)
        index += 2

    # 数据页
    for entry in entries:
        for sheet in entry["workloads"]:
            write_sheet(workbook, sheet)

    if out_path is None:
        base = os.path.splitext(os.path.basename(csv_paths[0]))[0]
        out_path = os.path.join(os.path.dirname(os.path.abspath(csv_paths[0])), base + "_判据.xlsx")
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    workbook.save(out_path)

    print("=" * 78)
    print("解析 + 判据完成")
    for entry in entries:
        print("  输入[{}]: {}".format(entry["kind"], entry["path"]))
    print("  输出: {}".format(out_path))
    print("  页: {}".format("、".join(workbook.sheetnames)))
    for entry in entries:
        field_count: Dict[str, int] = {}
        for item in entry["alarms"]:
            field_count[item.field_name] = field_count.get(item.field_name, 0) + 1
        print("  [{}] 告警 {} 条，去重后 {} 个字段".format(
            entry["kind"], len(entry["alarms"]), len(field_count)))
        for fname, count in sorted(field_count.items(), key=lambda kv: -kv[1]):
            print("        {:<36} 出现 {} 拍".format(fname, count))
    print("=" * 78)
    return out_path


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("用法: python report.py <csv> [<csv2>] [输出xlsx]")
        return
    out = None
    if args[-1].lower().endswith(".xlsx"):
        out = args[-1]
        args = args[:-1]
    if not args:
        print("至少要给一个 CSV")
        return
    build_report(args, out)


if __name__ == "__main__":
    main()
