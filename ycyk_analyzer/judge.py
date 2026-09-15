# -*- coding: utf-8 -*-
"""
judge.py —— 判据引擎：从合并表的「判据」列读规则，按标准格式求值。

判据住在**合并解析表**里（`spec/spec_merged_*.xlsx`），不在代码里 ——
**加判据 = 在 Excel 里改一格**，不用动 py。格式由 `tools/normalize_judges.py` 归一，共 8 种：

    正常值:X[,级:异常|告警]      值等于 X 即通过（多值用 | 分隔；支持 0x/0b/FF/中文枚举）
    正常范围:a~b[,级:...]        值落在 [a,b] 内即通过
    文本:词|词[,级:...]          值含这些词即命中（用于"值本身就是中文结论"的字段，如快遥 T 段）
    结构对应:帧序号=N            该消息必须出现在帧序号=N 的包里（进 frame 自证，不逐拍判）
    总体:有变化 / 总体:按历史基线  跨拍判据（V1 暂未启用，保留语义）
    无需判据 / 待定               不判 → 「暂不判据」

口诀：**判据只描述"什么算正常"，命中不了就是问题**；严重度（异常 / 告警）由 `,级:` 给。

两种判定：
    judge(...)      —— 瞬时（逐拍）：给一个值，返回 通过 / 告警 / 异常 / 暂不判据
    summarize(...)  —— 总体（跨拍）：给"异常拍数 / 总拍数"，返回一句总体结论
                       （V1 用通用口径：全程/持续/间歇/偶发，不依赖规则）

★ 读取健壮性：openpyxl 读不了（文件被腾讯文档等工具重写过样式）时，
  自动退回**直接解析 xlsx 内部 XML** —— 样式坏不影响数据。
"""

from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from openpyxl import load_workbook

OK = "通过"
WARN = "告警"
ERR = "异常"
NA = "暂不判据"

# report.py 里的数据块名 → 合并表的 sheet 名
SOURCE_TO_SHEET = {
    "T段-快遥": "标准快遥",
    "T段-慢遥": "标准慢遥51H",
    "slot0": "通道0（slot0）",
    "slot2": "通道1（slot2）",
    "slot3": "通道2（slot3）",
    "slot5": "通道3（slot5）",
}

# 各 sheet 的「参数名称」列（通道页名称在第 4 列，T 段页在第 1 列）
NAME_COL = {
    "标准快遥": 1,
    "标准慢遥51H": 1,
    "标准慢遥52H": 1,
    "标准慢遥53H": 1,
    "通道0（slot0）": 4,
    "通道1（slot2）": 4,
    "通道2（slot3）": 4,
    "通道3（slot5）": 4,
}

# 各 sheet 的「判据」列
JUDGE_COL = {
    "标准快遥": 4,
    "标准慢遥51H": 4,
    "标准慢遥52H": 4,
    "标准慢遥53H": 4,
    "通道0（slot0）": 14,
    "通道1（slot2）": 14,
    "通道2（slot3）": 14,
    "通道3（slot5）": 14,
}

KIND_VALUE = "value"
KIND_RANGE = "range"
KIND_TEXT = "text"
KIND_STRUCT = "struct"
KIND_SUMMARY = "summary"
KIND_NONE = "none"

POS_HINTS = ("正常", "成功", "可用", "有效", "完成", "上电", "使能")
NEG_HINTS = ("不正常", "异常", "失败", "故障", "过高", "过低", "错误", "无效",
             "未接入", "中断", "损坏", "告警", "失锁", "过功率", "不可用", "未成功")


def to_number(text: str) -> Optional[float]:
    """把「0x7FFFFF / 0b101 / FF / 3 / 1.5」这类写法统一转成数字；转不了返回 None。"""
    t = str(text).strip().lower()
    if not t:
        return None
    try:
        if t.startswith("0x"):
            return float(int(t, 16))
        if t.startswith("0b"):
            return float(int(t, 2))
        return float(t)
    except ValueError:
        pass
    try:
        return float(int(t, 16))   # 纯十六进制字符，如 FF
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 单条判据
# ---------------------------------------------------------------------------


@dataclass
class JudgeSpec:
    """一条判据（对应合并表判据列的一格）。"""

    raw: str
    kind: str
    level: str = WARN
    values: List[str] = field(default_factory=list)   # 正常值 / 文本词表
    low: Optional[float] = None
    high: Optional[float] = None
    frame_seq: Optional[int] = None
    summary_kind: str = ""

    def evaluate(self, value) -> str:
        """瞬时判定：返回 通过 / 告警 / 异常 / 暂不判据。"""
        text = "" if value is None else str(value).strip()

        if self.kind == KIND_VALUE:
            if not text:
                return NA
            got = to_number(text)
            # ★ 值不是数字时按中文语义判 —— 快遥 T 段的值是**解码后的中文**（"正常"/"异常"），
            #   而判据那格写的是位模式（正常值:1）。两者视角不同，这里做适配：
            #   含负面词 = 命中，含正面词 = 通过。
            if got is None:
                if any(w in text for w in NEG_HINTS):
                    return self.level
                if any(w in text for w in POS_HINTS):
                    return OK
                return NA
            # 数字比较（覆盖 0x / 0b / FF 与十进制混写）
            for want in self.values:
                want_num = to_number(want)
                if got is not None and want_num is not None:
                    if abs(got - want_num) < 1e-9:
                        return OK
                elif text == want.strip():
                    return OK
            return self.level

        if self.kind == KIND_RANGE:
            got = to_number(text)
            if got is None or self.low is None or self.high is None:
                return NA
            return OK if self.low <= got <= self.high else self.level

        if self.kind == KIND_TEXT:
            if not text:
                return NA
            if any(w and w in text for w in self.values):
                return self.level
            # 不含负面词：如果值本身是正面词就判通过，否则留白（如模式类枚举）
            if any(w in text for w in POS_HINTS):
                return OK
            return NA

        return NA   # 结构对应 / 总体 / 无需判据 → 不参与逐拍判

    def describe(self) -> str:
        """一句话说明这条判据（给报告用）。"""
        if self.kind == KIND_VALUE:
            return "正常值 = {}".format(" 或 ".join(self.values))
        if self.kind == KIND_RANGE:
            return "正常范围 {~{}".format(self.low, self.high)
        if self.kind == KIND_TEXT:
            return "值含「{}」即判{}".format("、".join(self.values), self.level)
        if self.kind == KIND_STRUCT:
            return "必须出现在帧序号 = {} 的包里".format(self.frame_seq)
        if self.kind == KIND_SUMMARY:
            return self.summary_kind
        return "不判"


def parse_judge(raw: str) -> JudgeSpec:
    """把判据列的一格文字解析成 JudgeSpec。"""
    text = (raw or "").strip()
    if not text:
        return JudgeSpec(raw=raw or "", kind=KIND_NONE)

    # 先摘掉 ,级:X
    level = WARN
    match = re.search(r",\s*级[:：]\s*(\S+)", text)
    if match:
        level = match.group(1).strip()
        text = text[: match.start()].strip()

    if text.startswith("无需判据") or text.startswith("待定"):
        return JudgeSpec(raw=raw or "", kind=KIND_NONE)

    if text.startswith("结构对应"):
        seq = re.search(r"帧序号\s*=\s*(\d)", text)
        return JudgeSpec(raw=raw or "", kind=KIND_STRUCT,
                         frame_seq=int(seq.group(1)) if seq else None)

    if text.startswith("总体:"):
        return JudgeSpec(raw=raw or "", kind=KIND_SUMMARY, summary_kind=text)

    if text.startswith("正常范围"):
        body = text.split(":", 1)[1] if ":" in text else ""
        parts = re.split(r"[~～]", body)
        if len(parts) == 2:
            return JudgeSpec(raw=raw or "", kind=KIND_RANGE, level=level,
                             low=to_number(parts[0]), high=to_number(parts[1]))
        return JudgeSpec(raw=raw or "", kind=KIND_NONE)

    if text.startswith("正常值"):
        body = text.split(":", 1)[1] if ":" in text else ""
        values = [v.strip() for v in body.split("|") if v.strip()]
        return JudgeSpec(raw=raw or "", kind=KIND_VALUE, level=level, values=values)

    if text.startswith("文本"):
        body = text.split(":", 1)[1] if ":" in text else ""
        values = [v.strip() for v in re.split(r"[|/、]", body) if v.strip()]
        return JudgeSpec(raw=raw or "", kind=KIND_TEXT, level=level, values=values)

    return JudgeSpec(raw=raw or "", kind=KIND_NONE)


# ---------------------------------------------------------------------------
# 判据表
# ---------------------------------------------------------------------------


class JudgeTable:
    """全部判据，按 (sheet 名, 字段名) 索引。"""

    def __init__(self, table: Dict[Tuple[str, str], JudgeSpec]):
        self.table = table

    def __len__(self) -> int:
        return len(self.table)

    def spec(self, source: str, field_name: str) -> Optional[JudgeSpec]:
        sheet = SOURCE_TO_SHEET.get(source, source)
        return self.table.get((sheet, field_name))

    def judge(self, source: str, field_name: str, value) -> str:
        """瞬时判定入口。没判据 / 明确无需判据 → 「暂不判据」。"""
        spec = self.spec(source, field_name)
        if spec is None:
            return NA
        return spec.evaluate(value)

    def describe(self, source: str, field_name: str) -> str:
        spec = self.spec(source, field_name)
        return spec.describe() if spec else ""

    def stats(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for spec in self.table.values():
            key = spec.kind if spec.kind != KIND_NONE else "无需判据"
            out[key] = out.get(key, 0) + 1
        return out


def summarize(alarm_count: int, total: int) -> str:
    """总体结论（跨拍，不依赖规则）：看异常拍数占整段的比例。"""
    if total <= 0 or alarm_count <= 0:
        return ""
    ratio = alarm_count / float(total)
    if alarm_count == total:
        return "全程异常"
    if ratio >= 0.9:
        return "持续异常"
    if ratio <= 0.05:
        return "偶发"
    return "间歇异常"


# ---------------------------------------------------------------------------
# 读取（openpyxl 优先，读不了就退回 XML 抢救）
# ---------------------------------------------------------------------------

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _rows_from_xml(path: str, sheet_name: str) -> List[List[str]]:
    """直接从 xlsx 内部 XML 读一个 sheet（绕过 openpyxl 的样式解析）。"""
    with zipfile.ZipFile(path) as z:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(_NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_NS + "t")))

        wb_xml = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_map = {r.get("Id"): r.get("Target") for r in rels}
        target = None
        for sh in wb_xml.iter(_NS + "sheet"):
            if sh.get("name") == sheet_name:
                target = rid_map.get(sh.get(_RELS + "id"))
                break
        if target is None:
            return []
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")

        root = ET.fromstring(z.read(target))
        cells: Dict[int, Dict[int, str]] = {}
        max_col = 0
        for row in root.iter(_NS + "row"):
            rno = int(row.get("r"))
            row_map: Dict[int, str] = {}
            for c in row.findall(_NS + "c"):
                m = re.match(r"([A-Z]+)(\d+)", c.get("r") or "")
                if not m:
                    continue
                col = 0
                for ch in m.group(1):
                    col = col * 26 + ord(ch) - 64
                t, v = c.get("t"), c.find(_NS + "v")
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    is_el = c.find(_NS + "is")
                    val = "".join(x.text or "" for x in is_el.iter(_NS + "t")) if is_el is not None else ""
                else:
                    val = v.text if v is not None and v.text is not None else ""
                row_map[col] = val
                max_col = max(max_col, col)
            cells[rno] = row_map

        return [[cells.get(r, {}).get(c, "") for c in range(1, max_col + 1)]
                for r in range(1, max(cells) + 1)] if cells else []


def _sheet_rows(path: str, sheet_name: str) -> List[List[str]]:
    """读一个 sheet 的所有行（值）；openpyxl 失败时自动退回 XML。"""
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        if sheet_name not in wb.sheetnames:
            return []
        return [list(r) for r in wb[sheet_name].iter_rows(values_only=True)]
    except Exception:
        return _rows_from_xml(path, sheet_name)


def default_spec_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "spec", "spec_merged_20260914.xlsx")


def load_judges(spec_path: Optional[str] = None) -> JudgeTable:
    """读合并表里全部判据，建索引。"""
    path = spec_path or default_spec_path()
    table: Dict[Tuple[str, str], JudgeSpec] = {}

    for sheet_name, name_col in NAME_COL.items():
        judge_col = JUDGE_COL.get(sheet_name)
        if judge_col is None:
            continue
        rows = _sheet_rows(path, sheet_name)
        for row in rows[1:]:
            if len(row) < max(name_col, judge_col):
                continue
            name = str(row[name_col - 1] or "").strip()
            raw = str(row[judge_col - 1] or "").strip()
            if not name or not raw:
                continue
            table[(sheet_name, name)] = parse_judge(raw)

    return JudgeTable(table)
