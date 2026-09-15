# -*- coding: utf-8 -*-
"""
align.py —— 对齐报告：把 CSV 里每个包解一遍，统计"自证通过率"。

不依赖外部工具：不拿外部产物逐格比对，而是每个包自己证明自己对（见 frame.py）。
通过率 100% = 消息定位、表定义、位序解码三者一致。

用法：python align.py <csv或目录> [...]；加 --dump <csv> <行号> 列出某行的全部字段值。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List

# Windows 控制台默认 GBK，强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from frame import SEQ_TO_SLOT, DecodedFrame, decode_frame, load_slots_by_seq  # noqa: E402
from table_csv import load_csv  # noqa: E402


@dataclass
class AlignResult:
    """一个 CSV 文件的对齐结果。"""

    path: str
    total: int = 0
    passed: int = 0
    skipped: str = ""                                         # 非 slot 包数据（如快遥）的说明
    failed: List[DecodedFrame] = field(default_factory=list)
    unknown_seq: List[int] = field(default_factory=list)      # 帧序号认不出来的行
    slot_counts: Dict[int, int] = field(default_factory=dict)
    message_hist: Dict[str, int] = field(default_factory=dict)
    csv_problems: List[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.passed * 100.0 / self.total if self.total else 0.0


def analyze_file(path: str, spec_map: Dict[int, object]) -> AlignResult:
    """把一个 CSV 文件里所有包解一遍。"""
    csv_data = load_csv(path)
    result = AlignResult(path=path, csv_problems=list(csv_data.problems))

    # 快遥那类数据没有 Z 段（本来就不是 slot 包），跳过 —— 它走 T 段列名映射那条路
    if not csv_data.is_slot_data:
        result.skipped = "无 Z 段（只有 {} 列 T 段），不是 slot 包数据".format(len(csv_data.t_columns))
        return result

    for row in csv_data.rows:
        result.total += 1
        seq = row.z_bytes[147]                     # 帧尾那一字节 = 帧序号
        slot_no = SEQ_TO_SLOT.get(seq)

        if slot_no is None or slot_no not in spec_map:
            result.unknown_seq.append(row.row_no)
            continue

        frame = decode_frame(bytes(row.z_bytes), spec_map[slot_no], row.row_no)

        result.slot_counts[slot_no] = result.slot_counts.get(slot_no, 0) + 1
        for msg in frame.messages:
            key = msg.type_id or "?"
            result.message_hist[key] = result.message_hist.get(key, 0) + 1

        if frame.ok:
            result.passed += 1
        else:
            result.failed.append(frame)

    return result


def print_result(result: AlignResult, max_fail_detail: int = 5) -> None:
    """打印单个文件的对齐结果。"""
    name = os.path.basename(result.path)

    if result.skipped:
        print("{}".format(name))
        print("    [跳过] {}".format(result.skipped))
        return

    flag = "通过" if result.passed == result.total and not result.csv_problems else "有问题"
    print("{}".format(name))
    print("    包数 {:<4} 自证通过 {:<4} ({:>5.1f}%)  失败 {:<3}  [{}]".format(
        result.total, result.passed, result.rate, result.total - result.passed, flag))

    if result.slot_counts:
        dist = "  ".join("slot{}= {}".format(k, result.slot_counts[k]) for k in sorted(result.slot_counts))
        print("    按 slot 分布: " + dist)

    if result.message_hist:
        hist = "  ".join(
            "{}×{}".format(k, v)
            for k, v in sorted(result.message_hist.items(), key=lambda kv: -kv[1])
        )
        print("    消息出现次数: " + hist)

    if result.unknown_seq:
        print("    !! 帧序号认不出来的行: {}".format(result.unknown_seq[:10]))

    if result.csv_problems:
        print("    !! CSV 读取问题 {} 条，前 3 条:".format(len(result.csv_problems)))
        for p in result.csv_problems[:3]:
            print("       - " + p)

    for frame in result.failed[:max_fail_detail]:
        print("    !! 第 {} 行（帧序号 {}，应为 slot{}）自证未过:".format(
            frame.row_no, frame.seq, frame.slot_no))
        for item in frame.failed_checks:
            print("       - {}: {}".format(item.name, item.detail))
    if len(result.failed) > max_fail_detail:
        print("    ...（另有 {} 个包未过，已省略）".format(len(result.failed) - max_fail_detail))


def dump_row(path: str, row_no: int, spec_map: Dict[int, object]) -> None:
    """把某一行的完整解析结果打出来，用于人工核对。"""
    csv_data = load_csv(path)
    if not 1 <= row_no <= len(csv_data.rows):
        print("行号超出范围（1~{}）".format(len(csv_data.rows)))
        return

    row = csv_data.rows[row_no - 1]
    seq = row.z_bytes[147]
    slot_no = SEQ_TO_SLOT.get(seq, -1)
    print("=" * 78)
    print("文件: {}".format(os.path.basename(path)))
    print("第 {} 行   DMTime={}   SatTime={}".format(row.row_no, row.dm_time, row.sat_time))
    print("帧序号 {} → slot{}   channelId={}   pknum={}   pklen={}".format(
        seq, slot_no, row.meta_int("channelId"), row.meta_int("pknum"), row.meta_int("pklen")))
    print("=" * 78)

    if slot_no not in spec_map:
        print("没有 slot{} 的表页，无法解析".format(slot_no))
        return

    frame = decode_frame(bytes(row.z_bytes), spec_map[slot_no], row.row_no)
    print("自证结果: {}".format("全部通过" if frame.ok else "有未通过项"))
    for item in frame.checks:
        print("    [{}] {} {}".format("OK" if item.ok else "!!", item.name, item.detail))

    for msg in frame.messages:
        print()
        print("--- 消息 type={} @偏移{}字节 ---".format(msg.label, msg.offset))
        for fld in msg.fields:
            mark = {"header": "头", "field": "  ", "padding": "填", "trailer": "尾"}.get(fld.role, "  ")
            print("    {} {:>2}bit  {:<44} = {}".format(mark, fld.bits, fld.name[:44], fld.value))


def collect_targets(args: List[str]) -> List[str]:
    """把参数里的文件和目录展开成 csv 文件清单。"""
    targets: List[str] = []
    for item in args:
        if os.path.isdir(item):
            for name in sorted(os.listdir(item)):
                if name.lower().endswith(".csv"):
                    targets.append(os.path.join(item, name))
        elif os.path.isfile(item):
            targets.append(item)
        else:
            print("找不到: " + item)
    return targets


def main() -> None:
    args = sys.argv[1:]

    spec_map = load_slots_by_seq()
    if not spec_map:
        print("没加载到任何 slot 表页，检查解析表路径")
        return

    if args and args[0] == "--dump":
        if len(args) < 3:
            print("用法: python align.py --dump <csv文件> <行号>")
            return
        dump_row(args[1], int(args[2]), spec_map)
        return

    # --brief：只打印"没 100% 通过"的文件（批量跑整个目录时用）
    brief = "--brief" in args
    args = [a for a in args if a != "--brief"]

    if not args:
        print("用法: python align.py <csv文件或目录> [...]")
        print("      python align.py --brief <目录>     只列出未全部通过的文件")
        print("      python align.py --dump <csv文件> <行号>")
        return

    targets = collect_targets(args)
    if not targets:
        print("没有找到 CSV 文件")
        return

    print("=" * 78)
    print("对齐报告（自证通过率）")
    print("用的解析表: 见 spec.py 的 default_spec_path()")
    print("=" * 78)

    total_all = passed_all = 0
    skipped_files = 0
    results: List[AlignResult] = []
    for path in targets:
        result = analyze_file(path, spec_map)
        results.append(result)
        if result.skipped:
            skipped_files += 1
            if not brief:
                print_result(result)
            continue

        total_all += result.total
        passed_all += result.passed

        if brief and result.total and result.passed == result.total:
            continue  # brief 模式下，100% 通过的文件不打印
        print_result(result)

    if len(results) > 1:
        print("-" * 78)
        rate = passed_all * 100.0 / total_all if total_all else 0.0
        print("汇总: 共 {} 个文件（其中 {} 个非 slot 数据已跳过），{} 个包，自证通过 {} ({:.1f}%)".format(
            len(results), skipped_files, total_all, passed_all, rate))
        bad = [r for r in results if not r.skipped and r.passed != r.total]
        if bad:
            print("未 100% 通过的文件 {} 个:".format(len(bad)))
            for r in bad:
                print("    {:<26} {}/{}  ({:.1f}%)".format(
                    os.path.basename(r.path), r.passed, r.total, r.rate))
        else:
            print("全部 slot 数据文件均 100% 通过")


if __name__ == "__main__":
    main()
