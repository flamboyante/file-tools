# -*- coding: utf-8 -*-
"""
table_csv.py —— 读遥测 CSV，按列名把内容分成三段：T 段 / Z 段 / 元数据。

CSV 结构（271 列，以 `慢遥1-*.csv` 为准）：

    列 0-1     DMTime, SatTime               时间
    列 2-112   TMXZJDT2001 .. TMXZJDT2111    111 列 = T 段（已是解码好的中文枚举或数值）
    列 113-260 TMXZJDZ2001 .. TMXZJDZ2148    148 列 = Z 段（每列一个字节，取值 0~255）
    列 261-270 apid/backFlag/.../ver         10 列元数据

Z 段一列 = 包里一个字节：TMXZJDZ2001 → 偏移 0，TMXZJDZ2148 → 偏移 147（帧序号）。
按顺序取 148 列拼成 list[int]，即一个完整的 slot 包。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, List

T_PREFIX = "TMXZJDT"     # T 段列名前缀
Z_PREFIX = "TMXZJDZ"     # Z 段列名前缀

TIME_COLUMNS = ("DMTime", "SatTime")

# 元数据列（慢遥 CSV 固定这 10 个）
META_COLUMNS = (
    "apid", "backFlag", "channelCount", "channelId", "oddEvenFlag",
    "pklen", "pknum", "secretFlag", "seiflag", "ver",
)

Z_BYTES = 148   # Z 段应有的列数 = 一个 slot 包的字节数


@dataclass
class TelemetryRow:
    """CSV 里的一行 = 一个 slot 包。"""

    row_no: int                 # 第几行（从 1 开始，不含表头）
    dm_time: str
    sat_time: str
    t_text: List[str]           # T 段各列的原始文本
    z_bytes: List[int]          # Z 段解析出来的 148 个字节
    meta: Dict[str, str]        # 元数据列

    def meta_int(self, name: str) -> int:
        """取元数据列的整数值；取不到返回 -1（比返回 0 更容易暴露异常）。"""
        try:
            return int(str(self.meta.get(name, "")).strip())
        except (TypeError, ValueError):
            return -1


@dataclass
class TelemetryCsv:
    """一个 CSV 文件读出来的全部内容。"""

    path: str
    header: List[str]
    rows: List[TelemetryRow] = field(default_factory=list)
    t_columns: List[str] = field(default_factory=list)
    z_columns: List[str] = field(default_factory=list)
    meta_columns: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)   # 读取时发现的问题（不做静默容错）

    @property
    def is_slot_data(self) -> bool:
        """是否含完整的 148 字节 slot 包。

        慢遥有（Z 段 148 列）；**快遥没有**（只有 68 列 T 段，没有 Z 段）——
        快遥走的是另一条路径：T 段列名映射，不做 slot/消息解析。
        """
        return len(self.z_columns) == Z_BYTES


def load_csv(path: str) -> TelemetryCsv:
    """读一个遥测 CSV。

    encoding 必须显式写 "utf-8"：文件是 UTF-8 无 BOM，用系统默认（Windows 为 GBK）
    解码会使中文列名乱码。
    """
    with open(path, "r", encoding="utf-8", newline="") as fh:
        raw = list(csv.reader(fh))

    if not raw:
        raise ValueError("CSV 是空的：" + path)

    header = [h.strip() for h in raw[0]]
    result = TelemetryCsv(path=path, header=header)
    result.t_columns = [h for h in header if h.startswith(T_PREFIX)]
    result.z_columns = [h for h in header if h.startswith(Z_PREFIX)]
    result.meta_columns = [h for h in header if h in META_COLUMNS]

    # Z 段 0 列 = 快遥那类数据（只有 T 段，本来就没有 slot 包），属正常；
    # 既不是 0 也不是 148 才是真问题。
    if len(result.z_columns) not in (0, Z_BYTES):
        result.problems.append(
            "Z 段列数异常：应为 0（无 Z 段）或 {}，实际 {} 列".format(Z_BYTES, len(result.z_columns))
        )

    index_of = {name: i for i, name in enumerate(header)}
    time_idx = [index_of.get(c, -1) for c in TIME_COLUMNS]
    t_idx = [index_of[c] for c in result.t_columns]
    z_idx = [index_of[c] for c in result.z_columns]
    meta_idx = {c: index_of[c] for c in result.meta_columns}

    for row_no, raw_row in enumerate(raw[1:], start=1):
        if not any(cell.strip() for cell in raw_row):
            continue  # 空行跳过

        if len(raw_row) != len(header):
            result.problems.append(
                "第 {} 行列数不对：{} ≠ {}".format(row_no, len(raw_row), len(header))
            )
            continue

        z_bytes: List[int] = []
        for i in z_idx:
            cell = raw_row[i].strip()
            try:
                value = int(cell)
            except ValueError:
                result.problems.append("第 {} 行 Z 段有非数字：{}".format(row_no, cell[:20]))
                value = -1
            if not 0 <= value <= 255:
                result.problems.append("第 {} 行 Z 段取值越界：{}".format(row_no, value))
            z_bytes.append(value)

        result.rows.append(
            TelemetryRow(
                row_no=row_no,
                dm_time=raw_row[time_idx[0]] if time_idx[0] >= 0 else "",
                sat_time=raw_row[time_idx[1]] if time_idx[1] >= 0 else "",
                t_text=[raw_row[i] for i in t_idx],
                z_bytes=z_bytes,
                meta={name: raw_row[i] for name, i in meta_idx.items()},
            )
        )

    return result
