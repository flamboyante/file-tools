# -*- coding: utf-8 -*-
"""
probe.py —— 规格表「体检」报告，回答三个问题：
    1. 表读通了没？         → 4 页的字段位长合计是否都等于 1184
    2. 每条消息对不对得上？ → 字段位长合计 vs 备注里声明的 length
    3. 判据能覆盖多少？     → 把「备注」列分类统计，看有多少条能直接变成判据

用法：python probe.py
"""

from __future__ import annotations

import re
import sys

# Windows 控制台默认 GBK，强制 UTF-8 输出，避免中文报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from spec import (  # noqa: E402
    EXPECTED_TOTAL_BITS,
    FieldSpec,
    MessageSpec,
    SlotSpec,
    default_spec_path,
    load_all_slots,
)

# ---------------------------------------------------------------------------
# 备注分类规则
#
# 备注列是"判据"的唯一来源，但写法五花八门。这里把它分成 5 类：
#   judge  备注里明确写了"哪个值算不正常" → 可以直接自动判据
#   enum   有"值:含义"的枚举映射，但没说哪个算异常 → 需要人工定
#   range  只给了取值范围/单位（那两列上下限是全空的）→ 属于阶段2
#   plain  纯描述（怎么赋值、从哪个寄存器读）→ 判不了
#   empty  空白
# ---------------------------------------------------------------------------

# 表示"好坏"的常用词。中文备注里判断状态是否正常，基本离不开这些字眼。
STATUS_WORDS = (
    "正常|异常|失败|未成功|失锁|过功率|故障|错误|损坏|未接入|中断|告警|报警|非法|无效"
)

# 形式 A：数字 + 分隔符 + (表示) + 好坏词    如 "0表示正常"、"3：失败"、"0，未失锁"
RE_VALUE_STATUS = re.compile(r"\d+\s*(?:[:：,，=]\s*)?(?:表示\s*)?(?:" + STATUS_WORDS + r")")

# 形式 B：明确的"为正常/为不正常"     如 "0:enabled为正常，否则为不正常"
RE_IS_OK = re.compile(r"为(?:不)?正常|表示(?:不)?正常")

# 形式 C：数字 + 冒号 + 文字（枚举映射）  如 "0:业务/1:维护"
RE_ENUM = re.compile(r"\d+\s*[:：]\s*\S")

# 形式 D：给了范围或单位
RE_RANGE = re.compile(r"\.\.|～|范围|单位|寄存器")

JUDGE = "judge"
ENUM = "enum"
RANGE = "range"
PLAIN = "plain"
EMPTY = "empty"

CATEGORY_LABEL = {
    JUDGE: "可自动判据",
    ENUM: "枚举待定",
    RANGE: "范围待定",
    PLAIN: "纯描述",
    EMPTY: "空白",
}


def classify_note(note: str) -> str:
    """把一条备注归类。按"信息量从高到低"的顺序判断，命中即返回。"""
    text = (note or "").strip()
    if not text:
        return EMPTY
    if RE_VALUE_STATUS.search(text) or RE_IS_OK.search(text):
        return JUDGE
    if RE_ENUM.search(text):
        return ENUM
    if RE_RANGE.search(text):
        return RANGE
    return PLAIN


def short(text: str, width: int = 46) -> str:
    """把长文本压成一行短摘要，方便打印。"""
    one_line = " / ".join(part.strip() for part in (text or "").splitlines() if part.strip())
    if len(one_line) <= width:
        return one_line
    return one_line[: width - 1] + "…"


# ---------------------------------------------------------------------------
# 报告第 1 部分：结构自检
# ---------------------------------------------------------------------------


def report_structure(slots: list) -> None:
    print("\n【1】结构自检（字段位长合计 必须 = {}）".format(EXPECTED_TOTAL_BITS))
    print("-" * 78)
    print("{:<18}{:>6}{:>8}{:>12}{:>12}   {}".format(
        "sheet", "消息数", "字段数", "位长合计", "页末校验", "结论"))
    for slot in slots:
        field_count = sum(len(m.payload_fields) for m in slot.messages)
        verdict = "通过" if slot.check_ok else "!! 不一致"
        print("{:<18}{:>6}{:>8}{:>12}{:>12}   {}".format(
            slot.sheet_name,
            len(slot.messages),
            field_count,
            slot.total_bits,
            slot.declared_total_bits,
            verdict,
        ))


# ---------------------------------------------------------------------------
# 报告第 2 部分：逐条消息的位长 vs 声明长度
# ---------------------------------------------------------------------------


def report_messages(slots: list) -> None:
    print("\n【2】每条消息：位长构成 vs 备注声明的 length")
    print("-" * 78)
    print("  说明：头 = 消息ID+消息长度(共32bit)；业务 = 真正要解析的字段；")
    print("        填充/帧尾 = 表里夹在消息之间的「预留」和「慢遥帧序号」，不算业务内容。")
    for slot in slots:
        print("\n{}   (通道{} / slot{})".format(slot.sheet_name, slot.channel_index, slot.slot_no))
        for msg in slot.messages:
            parts = ["头{}".format(msg.header_bits), "业务{}".format(msg.field_bits)]
            if msg.padding_bits:
                parts.append("填充{}".format(msg.padding_bits))
            if msg.trailer_bits:
                parts.append("帧尾{}".format(msg.trailer_bits))

            declared = msg.declared_bits
            if declared is None:
                declared_text, verdict = "   -", "?? 备注里没写 length"
            else:
                declared_text = "{:>4}".format(declared)
                verdict = "吻合" if msg.delta_bits == 0 else "!! 差 {:+#d} bit".format(msg.delta_bits)

            print("  type={:<9} 字段{:>3}个  合计{:>5} = {:<30} 声明{:<6} {}".format(
                msg.type_label, len(msg.payload_fields), msg.total_bits,
                "+".join(parts), declared_text, verdict))


# ---------------------------------------------------------------------------
# 报告第 3 部分：判据覆盖率
# ---------------------------------------------------------------------------


def report_note_coverage(slots: list) -> None:
    print("\n【3】备注判据覆盖率（决定这个项目能做到什么程度）")
    print("-" * 78)

    buckets = {JUDGE: [], ENUM: [], RANGE: [], PLAIN: [], EMPTY: []}
    for slot in slots:
        for msg in slot.messages:
            for fld in msg.payload_fields:
                buckets[classify_note(fld.note)].append((slot, msg, fld))

    total = sum(len(v) for v in buckets.values())
    if total == 0:
        print("没有字段？")
        return

    print("全部字段数：{}（不含消息ID/消息长度）。分类占比：\n".format(total))
    for key in (JUDGE, ENUM, RANGE, PLAIN, EMPTY):
        items = buckets[key]
        percent = len(items) * 100.0 / total
        print("  {:<10} {:>4} 条   {:>5.1f}%".format(CATEGORY_LABEL[key], len(items), percent))

    # 把"能直接判"和"稍加人工就能判"的两类样例列出来，方便人工复核
    for key in (JUDGE, ENUM):
        print("\n  ── {} 样例（最多 12 条）──".format(CATEGORY_LABEL[key]))
        for slot, msg, fld in buckets[key][:12]:
            print("    [{} type={}] {} → {}".format(
                slot.sheet_name, msg.type_label, fld.name, short(fld.note)))

    return buckets


# ---------------------------------------------------------------------------
# 报告第 4 部分：需要人拍板的事项
# ---------------------------------------------------------------------------


def report_attention(slots: list, buckets: dict) -> None:
    print("\n【4】需要你拍板 / 注意的事项")
    print("-" * 78)

    problems = []
    for slot in slots:
        if not slot.check_ok:
            problems.append("{}：位长合计 {} ≠ 页末校验 {} —— 表读错了，先查这里".format(
                slot.sheet_name, slot.total_bits, slot.declared_total_bits))
        for msg in slot.messages:
            if msg.declared_bits is not None and msg.delta_bits != 0:
                problems.append(
                    "{} type={}：业务+头 {} vs 声明 {}({}字节+4B头) → 差 {:+#d} bit".format(
                        slot.sheet_name, msg.type_label, msg.header_bits + msg.field_bits,
                        msg.declared_bits, msg.declared_bytes, msg.delta_bits))
            if msg.declared_bytes is None:
                problems.append("{} type={}：备注里没写 length".format(
                    slot.sheet_name, msg.type_label))

    if problems:
        for line in problems:
            print("  ! " + line)
    else:
        print("  （位长与声明全部吻合）")

    judge_like = len(buckets[JUDGE]) + len(buckets[ENUM])
    total = sum(len(v) for v in buckets.values()) or 1
    print("\n  判据可获得性：备注里能直接/稍加人工就能定判据的字段 {}/{} ({:.1f}%)".format(
        judge_like, total, judge_like * 100.0 / total))
    print("  剩下 {} 条是纯描述或空白 —— 这些列在阶段1 只能标『暂不判据』。".format(
        len(buckets[PLAIN]) + len(buckets[EMPTY])))


def main() -> None:
    path = default_spec_path()
    print("=" * 78)
    print("规格表体检报告")
    print("表文件：{}".format(path))
    print("=" * 78)

    slots = load_all_slots(path)
    if not slots:
        print("没读到任何通道页，检查 sheet 命名。")
        return

    report_structure(slots)
    report_messages(slots)
    buckets = report_note_coverage(slots)
    report_attention(slots, buckets)


if __name__ == "__main__":
    main()
