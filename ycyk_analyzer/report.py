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
from datetime import datetime  # noqa: E402
from typing import Dict, List, Optional, Tuple  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from frame import SEQ_TO_SLOT, decode_frame, load_slots_by_seq  # noqa: E402
from judge import load_judges, summarize  # noqa: E402
from t_segment import load_t_segments, pick_segment  # noqa: E402
from table_csv import load_csv  # noqa: E402

# ---------------------------------------------------------------------------
# 三态与配色（红=告警，绿=通过，无色=暂不判据）
# ---------------------------------------------------------------------------

OK = "通过"
ALARM = "告警"      # 次级：需要关注
ERR = "异常"        # 严重：必须处理
NA = "暂不判据"

FILL_OK = PatternFill("solid", fgColor="EAF3DE")      # 绿
FILL_ALARM = PatternFill("solid", fgColor="FAEEDA")   # 橙（告警）
FILL_ERR = PatternFill("solid", fgColor="FCEBEB")     # 红（异常）
FILL_NA = PatternFill("solid", fgColor="F1EFE8")      # 浅灰（没判据 / 没判定）
FONT_OK = Font(color="27500A", size=10)
FONT_ALARM = Font(color="854F0B", size=10)
FONT_ERR = Font(color="A32D2D", bold=True, size=10)
FONT_NA = Font(color="888780", size=10)
FONT_HEAD = Font(bold=True, size=10)
ALIGN_WRAP = Alignment(vertical="top", wrap_text=True)

# ---------------------------------------------------------------------------
# 判据：来自合并表的「判据」列（见 judge.py）—— 加判据 = 在 Excel 里改一格
# ---------------------------------------------------------------------------

JUDGES = load_judges()


def judge_field(source: str, name: str, value) -> str:
    """瞬时判据（逐拍）。

    source = 数据块名（T段-快遥 / T段-慢遥 / slot0 / slot3 / slot5），
    judge.py 负责把它映射到合并表的对应 sheet。
    """
    return JUDGES.judge(source, name, value)


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
            verdict_row.append(judge_field(sheet.title, fld.name, fld.raw))
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
                verdict_row.append(judge_field(sheet.title, spec_field.name, got.value))
        sheet.rows.append(row)
        sheet.verdicts.append(verdict_row)
    return sheet


def collect_alarms(sheet: SheetData) -> List[AlarmItem]:
    """把一张表里判定为"告警"的单元格收集起来。"""
    out: List[AlarmItem] = []
    for r_idx, verdict_row in enumerate(sheet.verdicts):
        for c_idx, verdict in enumerate(verdict_row):
            if verdict in (ALARM, ERR):
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


def write_report_sheet(workbook, entries: List[Dict], index: int = 0) -> None:
    """首页「分析报告」：人话结论 —— 数据来源、规模、发现的问题及其持续性。

    这一页是给"看结论的人"准备的：不需要理解 T 段/BMU/slot 这些概念，
    只要看这一页就知道"这批数据有没有问题、什么问题、多严重"。
    """
    ws = workbook.create_sheet(title="分析报告", index=index)

    lines: List[List[str]] = []
    lines.append(["ycyk 遥测分析报告", ""])
    lines.append(["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    lines.append(["", ""])

    lines.append(["— 数据来源 —", ""])
    total_summary = []
    for entry in entries:
        rows = entry["data"].rows
        first_time = rows[0].dm_time if rows else "（无数据）"
        last_time = rows[-1].dm_time if rows else ""
        lines.append([entry["kind"], os.path.basename(entry["path"])])
        lines.append(["", "包数 {}　时间范围 {} ~ {}".format(len(rows), first_time, last_time)])
        total_summary.append((entry, len(rows)))
    lines.append(["", ""])

    lines.append(["— 结论 —", ""])
    any_alarm = False
    for entry, n_rows in total_summary:
        fields: Dict[str, Dict] = {}
        for alarm in entry["alarms"]:
            info = fields.setdefault(alarm.field_name, {
                "count": 0, "total": alarm.total_rows or n_rows, "level": alarm.verdict,
                "source": alarm.source, "value": alarm.value, "note": alarm.note,
            })
            info["count"] += 1

        if not fields:
            lines.append(["{}：未发现异常（{} 个包全部通过判据）".format(entry["kind"], n_rows)])
            continue

        any_alarm = True
        lines.append(["{}：发现 {} 个字段异常".format(entry["kind"], len(fields))])
        for name, info in sorted(fields.items(), key=lambda kv: -kv[1]["count"]):
            ratio = info["count"] * 100.0 / info["total"] if info["total"] else 0.0
            if ratio >= 99:
                span = "全程异常（持续性）"
            elif ratio >= 90:
                span = "持续异常"
            elif ratio <= 5:
                span = "偶发（{} 拍）".format(info["count"])
            else:
                span = "间歇异常"
            lines.append([
                "",
                "【{}】{}".format(info["level"], name),
            ])
            lines.append([
                "",
                "        异常 {}/{} 拍（{:.1f}%）· {} · 出现值「{}」".format(
                    info["count"], info["total"], ratio, span, info["value"]),
            ])
    if not any_alarm:
        lines.append(["", "两组数据均未发现异常。"])

    lines.append(["", ""])
    lines.append(["— 说明 —", ""])
    lines.append(["", "判据来自解析表「判据」列（异常=严重，需处理；告警=次级，需关注）"])
    lines.append(["", "「异常 x/y 拍」= 该字段在这批数据的 y 个采样包里，有 x 个被判为异常"])
    lines.append(["", "※ BMU 字段（来自 slot0/3/5）的 y 是「该 slot 的包数」，不是全组的包数"])
    lines.append(["", "其余页：告警汇总（按字段聚合）/ 告警明细（逐拍）/ T段数据 / BMU数据（slot）"])

    for row_idx, row in enumerate(lines, start=1):
        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    ws.cell(row=1, column=1).font = Font(bold=True, size=13)
    for row_idx, row in enumerate(lines, start=1):
        if row and str(row[0]).startswith("—"):
            ws.cell(row=row_idx, column=1).font = Font(bold=True, size=11)

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 96


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
            if verdict == ERR:
                cell.fill = FILL_ERR
                cell.font = FONT_ERR
            elif verdict == ALARM:
                cell.fill = FILL_ALARM
                cell.font = FONT_ALARM
            elif verdict == OK:
                cell.fill = FILL_OK
                cell.font = FONT_OK
            elif verdict == NA:
                # 没判据 / 没判定 → 浅灰（小K 要求：跟"有判据且通过"的绿区分开）
                cell.fill = FILL_NA
                cell.font = FONT_NA

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
                        "value": item.value, "note": item.note,
                        "total": item.total_rows, "verdict": item.verdict}
            order.append(key)
        agg[key]["count"] = int(agg[key]["count"]) + 1
        agg[key]["last"] = item.time

    ws = workbook.create_sheet(title="告警汇总-{}".format(kind), index=index)
    headers = ["数据块", "字段", "判定", "命中拍数", "总拍数", "总体结论", "首次时间", "末次时间", "值", "判据说明"]
    ws.append(headers)
    for idx in range(1, len(headers) + 1):
        ws.cell(row=1, column=idx).font = FONT_HEAD
        ws.cell(row=1, column=idx).alignment = ALIGN_WRAP
    ws.freeze_panes = "A2"

    for r_idx, key in enumerate(order, start=2):
        entry = agg[key]
        count = int(entry["count"])
        total = int(entry["total"])
        verdict = str(entry["verdict"])
        # ★ 总体结论（跨拍）：通用口径 —— 看命中拍数占整段的比例
        summary = summarize(count, total)
        values = [key[0], key[1], verdict, count, total, summary,
                  entry["first"], entry["last"], entry["value"], _flat(str(entry["note"]))]
        for c_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.alignment = ALIGN_WRAP
            if c_idx == 2:
                cell.font = Font(bold=True, size=10)
            elif c_idx == 3:
                if verdict == ERR:
                    cell.fill = FILL_ERR
                    cell.font = FONT_ERR
                elif verdict == ALARM:
                    cell.fill = FILL_ALARM
                    cell.font = FONT_ALARM
            elif c_idx == 6 and summary:
                cell.font = FONT_ERR if ("持续" in summary or "全程" in summary) else FONT_ALARM
    for c_idx, width in enumerate([10, 30, 8, 10, 8, 12, 22, 22, 12, 44], start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = width
    ws.cell(row=max(len(order) + 2, 4), column=1,
            value="来源：{}　（同一字段只占一行；「总体结论」按命中拍数占比：全程 / 持续≥90% / 间歇 / 偶发≤5%）".format(
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
                if item.verdict == ERR:
                    cell.fill = FILL_ERR
                    cell.font = FONT_ERR
                elif item.verdict == ALARM:
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

    # 首页：分析报告（人话结论）
    write_report_sheet(workbook, entries, 0)

    # 告警页：快、慢各一对
    index = 1
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
