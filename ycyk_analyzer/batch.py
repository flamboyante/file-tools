# -*- coding: utf-8 -*-
"""
batch.py —— 批量解析一个目录：自动配对快遥/慢遥，逐组解析 + 判据，出一份跨文件总览。

输出一个 xlsx（4 页）：
    批量总览        按「字段」聚合 —— 该异常是长期存在还是偶发
    按文件          每对文件一行（包数 / 自证通过 / 告警 / 异常 / 状态）
    全部告警明细     逐条，带来源文件与日期
    跳过清单        源文件本身有问题的 —— 不解析、记下原因，不拖累整体

源文件容错：CSV 读不了 / Z 段列数不对 / 慢遥自证通过率低于 SKIP_PASS_RATE（90%）→
跳过该文件并记入跳过清单。

配对规则：文件名尾部 "0914-00" 作为配对键
    `快遥-0914-00.csv` ↔ `慢遥1-0914-00.csv` → 键 0914-00

用法：python batch.py <数据目录> [输出xlsx]
"""

from __future__ import annotations

import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from align import analyze_file as align_file
from frame import load_slots_by_seq
from report import (
    ALARM,
    ALIGN_WRAP,
    ERR,
    FILL_ALARM,
    FILL_ERR,
    FONT_ALARM,
    FONT_ERR,
    FONT_HEAD,
    analyze_one,
    use_spec,
)
from spec import spec_fingerprint
from table_csv import load_csv
from t_segment import load_t_segments

SKIP_PASS_RATE = 0.90        # 慢遥自证通过率低于此值 → 判为源文件格式异常，跳过
FAST_T_COLUMNS = 68          # 快遥 T 段应有列数

RE_KEY = re.compile(r"(\d{4}-\d{2})$")


def pair_key(filename: str) -> str:
    """从文件名里取出配对键：`快遥-0914-00.csv` → `0914-00`。"""
    base = os.path.splitext(os.path.basename(filename))[0]
    match = RE_KEY.search(base)
    return match.group(1) if match else base


def pretty_date(key: str) -> str:
    """`0914-00` → `09-14`（给报告显示用）。"""
    if len(key) >= 4 and key[:4].isdigit():
        return "{}-{}".format(key[:2], key[2:4])
    return key


@dataclass
class FileOutcome:
    """一个文件的处理结果。"""

    path: str
    kind: str                       # 快遥 / 慢遥
    key: str
    skipped: str = ""               # 非空 = 被跳过，这里是原因
    alarms: List = field(default_factory=list)
    total_frames: int = 0
    passed_frames: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def pass_rate(self) -> float:
        return self.passed_frames * 100.0 / self.total_frames if self.total_frames else 0.0

    def count_of(self, verdict: str) -> int:
        return sum(1 for a in self.alarms if a.verdict == verdict)


def scan_directory(directory: str) -> Dict[str, Dict[str, str]]:
    """扫描目录，返回 {配对键: {"快遥": path, "慢遥": path}}。"""
    groups: Dict[str, Dict[str, str]] = {}
    for name in sorted(os.listdir(directory)):
        if not name.lower().endswith(".csv"):
            continue
        path = os.path.join(directory, name)
        if name.startswith("快遥"):
            kind = "快遥"
        elif name.startswith("慢遥"):
            kind = "慢遥"
        else:
            continue
        groups.setdefault(pair_key(name), {})[kind] = path
    return groups


def process_one(path: str, kind: str, key: str, t_segments, spec_map,
                threshold: float = SKIP_PASS_RATE) -> FileOutcome:
    """处理单个文件；源文件有问题就返回带 skipped 原因的结果。"""
    outcome = FileOutcome(path=path, kind=kind, key=key)

    # ---- 预检：能不能读、结构对不对 ----
    try:
        data = load_csv(path)
    except Exception as exc:                      # 读都读不了 → 跳过
        outcome.skipped = "读取失败：{}".format(exc)
        return outcome

    outcome.total_frames = len(data.rows)

    if kind == "慢遥":
        if not data.is_slot_data:
            outcome.skipped = "Z 段列数不是 148（实际 {}）—— 源文件结构不对".format(len(data.z_columns))
            return outcome
        # 自证通过率：正常文件为 100%，低于阈值说明源文件格式异常
        align = align_file(path, spec_map)
        outcome.passed_frames = align.passed
        if align.total and (align.passed / float(align.total)) < threshold:
            outcome.skipped = "自证通过率 {:.0%}（低于 {:0%}）—— 源文件格式异常".format(
                align.passed * 100.0 / align.total, threshold)
            return outcome
    else:
        if len(data.t_columns) != FAST_T_COLUMNS:
            outcome.skipped = "T 段列数 {} ≠ {} —— 源文件结构不对".format(
                len(data.t_columns), FAST_T_COLUMNS)
            return outcome

    # ---- 正式解析 + 判据 ----
    entry = analyze_one(path, t_segments, spec_map)
    outcome.alarms = entry["alarms"]
    return outcome


def run_batch(directory: str, out_path: Optional[str] = None,
              threshold: float = SKIP_PASS_RATE,
              progress: Optional[Callable[[int, int, str], None]] = None,
              spec_path: Optional[str] = None) -> str:
    """批量处理一个目录。progress(已完成组数, 总组数, 当前文件名) 供界面显示进度。

    spec_path 指定解析表；None = 自动搜索（外置优先，见 spec.py）。
    """
    groups = scan_directory(directory)
    if not groups:
        raise ValueError("目录里没找到 快遥*.csv / 慢遥*.csv：" + directory)

    use_spec(spec_path)                       # 判据表跟着换
    t_segments = load_t_segments(spec_path)
    spec_map = load_slots_by_seq(spec_path)

    keys = sorted(groups)
    outcomes: List[FileOutcome] = []
    for idx, key in enumerate(keys, start=1):
        paths = groups[key]
        for kind in ("快遥", "慢遥"):
            path = paths.get(kind)
            if not path:
                continue
            outcome = process_one(path, kind, key, t_segments, spec_map, threshold)
            outcomes.append(outcome)
            if progress:
                progress(idx, len(keys), outcome.name)

    # ---- 写 xlsx ----
    if out_path is None:
        stamp = os.path.basename(os.path.abspath(directory).rstrip("\\/")) or "batch"
        out_path = os.path.join(os.path.dirname(os.path.abspath(directory)),
                                "批量总览_{}.xlsx".format(stamp))
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)

    workbook = Workbook()
    workbook.remove(workbook.active)
    write_overview(workbook, outcomes, len(keys), os.path.basename(directory), spec_path)
    write_by_file(workbook, outcomes)
    write_details(workbook, outcomes)
    write_skipped(workbook, outcomes)
    workbook.save(out_path)

    # ---- 终端汇总 ----
    ok = [o for o in outcomes if not o.skipped]
    skipped = [o for o in outcomes if o.skipped]
    n_alarm = sum(o.count_of(ALARM) for o in ok)
    n_err = sum(o.count_of(ERR) for o in ok)
    print("=" * 78)
    print("批量完成：{} 组（{} 个文件）".format(len(keys), len(outcomes)))
    print("  成功解析 {} 个 · 跳过 {} 个".format(len(ok), len(skipped)))
    print("  告警 {} 条 · 异常 {} 条".format(n_alarm, n_err))
    fields = aggregate(outcomes)
    print("  涉及字段 {} 个".format(len(fields)))
    for name, info in sorted(fields.items(), key=lambda kv: -kv[1]["files"])[:15]:
        print("    {:<34} {} 个文件 / {} 条 · {} · {}".format(
            name[:34], info["files"], info["count"], info["level"], info["span"]))
    print("  输出: {}".format(out_path))
    print("=" * 78)
    return out_path


# ---------------------------------------------------------------------------
# 聚合与写表
# ---------------------------------------------------------------------------


def aggregate(outcomes: List[FileOutcome]) -> Dict[str, Dict]:
    """按字段聚合所有告警 —— 这是"长期还是偶发"的答案。"""
    fields: Dict[str, Dict] = {}
    for outcome in outcomes:
        if outcome.skipped:
            continue
        for alarm in outcome.alarms:
            info = fields.setdefault(alarm.field_name, {
                "files": 0, "count": 0, "level": alarm.verdict,
                "keys": set(), "first": outcome.key, "last": outcome.key,
            })
            info["count"] += 1
            info["keys"].add(outcome.key)
            info["files"] = len(info["keys"])
            if outcome.key < info["first"]:
                info["first"] = outcome.key
            if outcome.key > info["last"]:
                info["last"] = outcome.key
    for info in fields.values():
        n = info["files"]
        info["span"] = "单次出现" if n <= 1 else (
            "跨 {} 次采集".format(n) if n < 5 else "长期存在（{} 次）".format(n))
    return fields


def _style_sheet(ws, widths: List[int], freeze: str = "A2") -> None:
    ws.freeze_panes = freeze
    for idx in range(1, len(widths) + 1):
        ws.cell(row=1, column=idx).font = FONT_HEAD
        ws.cell(row=1, column=idx).alignment = ALIGN_WRAP
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width


def write_overview(workbook, outcomes: List[FileOutcome], group_count: int, folder: str,
                   spec_path: Optional[str] = None) -> None:
    ws = workbook.create_sheet(title="批量总览", index=0)
    headers = ["字段", "判定", "涉及文件数", "总条数", "采集跨度", "首次", "末次"]
    ws.append(headers)

    fields = aggregate(outcomes)
    for name, info in sorted(fields.items(), key=lambda kv: (-kv[1]["files"], -kv[1]["count"])):
        ws.append([name, info["level"], info["files"], info["count"], info["span"],
                   pretty_date(info["first"]), pretty_date(info["last"])])
        row = ws.max_row
        cell = ws.cell(row=row, column=2)
        if info["level"] == ERR:
            cell.fill = FILL_ERR
            cell.font = FONT_ERR
        else:
            cell.fill = FILL_ALARM
            cell.font = FONT_ALARM

    _style_sheet(ws, [34, 8, 10, 8, 18, 8, 8])
    ws.cell(row=ws.max_row + 2, column=1,
            value="来源目录：{}　共 {} 组；「采集跨度」按涉及的文件数给（单次/跨 N 次/长期存在）".format(
                folder, group_count)).font = Font(size=9, italic=True)
    ws.cell(row=ws.max_row + 1, column=1,
            value="判据表：{}".format(spec_fingerprint(spec_path))).font = Font(size=9, italic=True)


def write_by_file(workbook, outcomes: List[FileOutcome]) -> None:
    ws = workbook.create_sheet(title="按文件")
    ws.append(["文件", "类型", "日期", "包数", "自证通过", "告警", "异常", "状态"])
    for outcome in sorted(outcomes, key=lambda o: (o.key, o.kind)):
        status = "跳过：" + outcome.skipped if outcome.skipped else "OK"
        ws.append([
            outcome.name, outcome.kind, pretty_date(outcome.key), outcome.total_frames,
            "{:.0f}%".format(outcome.pass_rate) if outcome.kind == "慢遥" and not outcome.skipped else "-",
            outcome.count_of(ALARM), outcome.count_of(ERR), status,
        ])
        row = ws.max_row
        if outcome.skipped:
            ws.cell(row=row, column=8).fill = FILL_ERR
            ws.cell(row=row, column=8).font = FONT_ERR
        elif outcome.count_of(ERR):
            ws.cell(row=row, column=7).fill = FILL_ERR
            ws.cell(row=row, column=7).font = FONT_ERR
        elif outcome.count_of(ALARM):
            ws.cell(row=row, column=6).fill = FILL_ALARM
            ws.cell(row=row, column=6).font = FONT_ALARM
    _style_sheet(ws, [24, 8, 8, 8, 10, 8, 8, 46])


def write_details(workbook, outcomes: List[FileOutcome]) -> None:
    ws = workbook.create_sheet(title="全部告警明细")
    ws.append(["文件", "日期", "数据块", "时间", "字段", "值", "判定", "判据说明"])
    for outcome in sorted(outcomes, key=lambda o: (o.key, o.kind)):
        if outcome.skipped:
            continue
        for alarm in outcome.alarms:
            ws.append([outcome.name, pretty_date(outcome.key), alarm.source, alarm.time,
                       alarm.field_name, alarm.value, alarm.verdict,
                       " ".join((alarm.note or "").splitlines())[:120]])
            row = ws.max_row
            cell = ws.cell(row=row, column=7)
            if alarm.verdict == ERR:
                cell.fill = FILL_ERR
                cell.font = FONT_ERR
            else:
                cell.fill = FILL_ALARM
                cell.font = FONT_ALARM
    _style_sheet(ws, [24, 8, 10, 22, 30, 14, 8, 50])


def write_skipped(workbook, outcomes: List[FileOutcome]) -> None:
    ws = workbook.create_sheet(title="跳过清单")
    ws.append(["文件", "类型", "日期", "包数", "跳过原因"])
    skipped = [o for o in outcomes if o.skipped]
    for outcome in sorted(skipped, key=lambda o: (o.key, o.kind)):
        ws.append([outcome.name, outcome.kind, pretty_date(outcome.key),
                   outcome.total_frames, outcome.skipped])
    _style_sheet(ws, [24, 8, 8, 8, 60])
    if not skipped:
        ws.cell(row=2, column=1, value="（无跳过文件）")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("用法: python batch.py <数据目录> [输出xlsx]")
        return
    run_batch(args[0], args[1] if len(args) > 1 else None)


if __name__ == "__main__":
    main()
