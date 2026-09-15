# -*- coding: utf-8 -*-
"""
rules.py —— 判据规则引擎（规则全部来自 `rules.csv`，代码里不硬编码）。

为什么要这样：
    判据是业务知识，会一直变（加字段、调阈值、改口径）。写在 py 里就得改代码；
    搬到 `rules.csv` 之后 —— **加判据 = 在 Excel 里加一行**。

`rules.csv` 的列：

    启用        是 / 否（开关。规则先写好、没定论就填"否"）
    匹配字段    通配符，如 `*状态`、`*心跳*`、`SSD*电流`
    判据范围    **瞬时** / **总体** / **两者**
                  · 瞬时：逐拍判 → 用于明细页着色
                  · 总体：只看整段统计 → 用于"汇总结论"
                  · 两者：两边都判
    值类型      文本 / 数值 / 枚举 / 统计（"统计"只用在总体规则）
    条件        文本：`含(异常|失败)`           值里出现任一个即命中
                数值：`>0`、`>=100`、`在[20,80]外`
                枚举：`0=正常;1=过高;2=过低`    值先映射成含义，再按含义里的词判好坏
                统计：`异常拍数>0`、`异常比例>=0.9`
    结论        告警 / 通过（文本、数值用）；枚举类填 `按映射`；总体类可写 `持续告警`
    说明        写给人看的备注

★ 两道防误报的保险（都来自实测教训）：
    1. **文本类必须过"备注对照"门槛**：字段备注里要**同时**出现正面词和负面词
       （如 `1：正常：0：异常`），才认为这字段能判好坏。
       反例：`基站重构来源` 的备注是「…；11：无效」，「无效」只是枚举里的合法取值，
       不是异常 —— 不加门槛会冒出一大堆误报（实测 271 条 vs 15 条）。
       想绕开就把它写成"枚举"型，直接写死映射。
    2. **总体判据建立在瞬时判据之上**：先逐拍判出"异常拍数"，再按统计口径下结论。
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

OK = "通过"
ALARM = "告警"
NA = "暂不判据"

SCOPE_INSTANT = "瞬时"
SCOPE_SUMMARY = "总体"
SCOPE_BOTH = "两者"

KIND_TEXT = "文本"
KIND_NUMBER = "数值"
KIND_ENUM = "枚举"
KIND_STAT = "统计"

NEGATIVE_WORDS = (
    "异常", "失败", "过高", "过低", "错误", "故障", "无效",
    "未接入", "中断", "损坏", "告警", "报警", "失锁", "过功率", "未成功",
)
POSITIVE_WORDS = ("正常", "成功", "有效", "可用", "完成", "上电", "使能")

TRUE_WORDS = ("是", "1", "true", "True", "Y", "y", "✓")


def wildcard_match(pattern: str, name: str) -> bool:
    """通配符匹配：`*心跳*` 命中 `KA发送天线心跳状态`。"""
    expr = "^" + "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern.strip()) + "$"
    return re.match(expr, name) is not None


def _hit_words(text: str, words) -> bool:
    return any(w in text for w in words)


def compare(op: str, left: float, right) -> bool:
    """统一的比较：op ∈ > >= < <= = outside。"""
    if op == "outside":
        low, high = right          # type: ignore
        return left < low or left > high
    return {
        ">": left > right, ">=": left >= right,
        "<": left < right, "<=": left <= right,
        "=": left == right,
    }[op]


@dataclass
class Rule:
    """一条判据规则（对应 rules.csv 的一行）。"""

    enabled: bool
    pattern: str
    scope: str
    kind: str
    condition: str
    verdict: str
    note: str = ""
    row_no: int = 0

    # ---------------- 条件解析 ----------------

    def _text_words(self) -> List[str]:
        match = re.search(r"含\(([^)]*)\)", self.condition)
        if not match:
            return []
        return [w.strip() for w in re.split(r"[|,，;；]", match.group(1)) if w.strip()]

    def _enum_map(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for part in re.split(r"[;；]", self.condition):
            if "=" not in part:
                continue
            key, _, val = part.partition("=")
            mapping[key.strip()] = val.strip()
        return mapping

    def _number_cond(self) -> Optional[Tuple[str, object]]:
        match = re.match(r"^\s*(>=|<=|>|<|=)\s*(-?\d+(?:\.\d+)?)\s*$", self.condition)
        if match:
            return match.group(1), float(match.group(2))
        match = re.match(r"^\s*在\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]外\s*$", self.condition)
        if match:
            return "outside", (float(match.group(1)), float(match.group(2)))
        return None

    # ---------------- 瞬时判定 ----------------

    def judge_instant(self, value, note: str) -> Optional[str]:
        """逐拍判。命中返回 OK / ALARM，不适用返回 None。"""
        text = "" if value is None else str(value).strip()

        if self.kind == KIND_TEXT:
            # ★ 门槛：备注里得同时有正面词和负面词，才认为这字段能判好坏
            hint = note or ""
            if not (_hit_words(hint, NEGATIVE_WORDS) and _hit_words(hint, POSITIVE_WORDS)):
                return None
            words = self._text_words()
            if not words or not text or not _hit_words(text, tuple(words)):
                return None
            return self.verdict if self.verdict in (OK, ALARM) else ALARM

        if self.kind == KIND_ENUM:
            mapping = self._enum_map()
            if text not in mapping:
                return None
            meaning = mapping[text]
            if _hit_words(meaning, NEGATIVE_WORDS):
                return ALARM
            if _hit_words(meaning, POSITIVE_WORDS):
                return OK
            return None

        if self.kind == KIND_NUMBER:
            try:
                number = float(text)
            except (TypeError, ValueError):
                return None
            cond = self._number_cond()
            if cond is None:
                return None
            if compare(cond[0], number, cond[1]):
                return self.verdict if self.verdict in (OK, ALARM) else ALARM
            return None

        return None

    # ---------------- 总体判定 ----------------

    def judge_summary(self, total: int, alarm_count: int) -> Optional[str]:
        """按统计口径下结论。命中返回结论文字（如"持续告警"），否则 None。"""
        if self.kind != KIND_STAT or total <= 0:
            return None
        cond = re.sub(r"\s+", "", self.condition)
        ratio = alarm_count / float(total)

        match = re.match(r"^异常拍数(>=|<=|>|<|=)(\d+)$", cond)
        if match:
            return self.verdict if compare(match.group(1), alarm_count, float(match.group(2))) else None

        match = re.match(r"^异常比例(>=|<=|>|<|=)(\d+(?:\.\d+)?)$", cond)
        if match:
            return self.verdict if compare(match.group(1), ratio, float(match.group(2))) else None

        return None


class Ruleset:
    """一组规则。按顺序匹配，第一条命中的说了算。"""

    def __init__(self, rules: List[Rule]):
        self.rules = [r for r in rules if r.enabled]

    @property
    def count(self) -> int:
        return len(self.rules)

    def judge(self, field_name: str, value, note: str = "") -> str:
        """瞬时判定（用于明细页着色）。没规则命中就返回「暂不判据」。"""
        for rule in self.rules:
            if rule.scope not in (SCOPE_INSTANT, SCOPE_BOTH):
                continue
            if not wildcard_match(rule.pattern, field_name):
                continue
            verdict = rule.judge_instant(value, note)
            if verdict is not None:
                return verdict
        return NA

    def summarize(self, field_name: str, total: int, alarm_count: int) -> Optional[str]:
        """总体判定（用于汇总结论）。没规则命中返回 None。"""
        for rule in self.rules:
            if rule.scope not in (SCOPE_SUMMARY, SCOPE_BOTH):
                continue
            if not wildcard_match(rule.pattern, field_name):
                continue
            verdict = rule.judge_summary(total, alarm_count)
            if verdict:
                return verdict
        return None


def default_rules_path() -> str:
    """rules.csv 与本模块同目录。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.csv")


def load_rules(path: Optional[str] = None) -> Ruleset:
    """读 rules.csv。

    ★ 用 utf-8-sig 打开：兼容 Excel 另存出的带 BOM 的 CSV（不带 BOM 时中文会乱码）。
    """
    rules_path = path or default_rules_path()
    if not os.path.isfile(rules_path):
        return Ruleset([])

    rules: List[Rule] = []
    with open(rules_path, "r", encoding="utf-8-sig", newline="") as fh:
        for row_no, row in enumerate(csv.DictReader(fh), start=2):
            # 兼容列名里残留 BOM 的情况 —— Excel / 编辑器另存 CSV 时的常见坑
            row = {(k or "").lstrip("\ufeff").strip(): v for k, v in row.items()}
            pattern = str(row.get("匹配字段") or "").strip()
            if not pattern:
                continue
            rules.append(Rule(
                enabled=str(row.get("启用") or "").strip() in TRUE_WORDS,
                pattern=pattern,
                scope=str(row.get("判据范围") or SCOPE_INSTANT).strip() or SCOPE_INSTANT,
                kind=str(row.get("值类型") or KIND_TEXT).strip() or KIND_TEXT,
                condition=str(row.get("条件") or "").strip(),
                verdict=str(row.get("结论") or "").strip(),
                note=str(row.get("说明") or "").strip(),
                row_no=row_no,
            ))
    return Ruleset(rules)
