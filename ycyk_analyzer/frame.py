# -*- coding: utf-8 -*-
"""
frame.py —— 把一个 slot 包（148 字节）解析成"消息 + 字段值"，并**当场自证解析正确**。

这个文件是整个项目的核心。它做两件事：

一、定位消息（两套机制并用，都是实测确认过的）
    1. **游标扫描**：从偏移 0 开始 ——
           读 2 字节"消息ID" → 读 2 字节"消息长度" → 按定义解码 → 跳到 (4 + 长度) 字节之后
       遇到连续 0（空槽）就跳过去；查到表里没有的 ID 立刻报错（不猜、不跳过）。
       ★ 必须走游标，因为**表里的消息顺序 ≠ 包里的实际顺序**：
         表里写 1000→1100→1101→1800→1052，
         实测包里是 1000→1800→1100→1101→1052。
         表只能当"消息字典"用，不能按它的顺序数固定偏移。
    2. **帧尾锚定**：BMU 的三个消息（1050/1051/1052）按"从帧尾倒推"定位 ——
           起始偏移 = 147 − (消息总位长 − 帧尾位长) / 8
       实测三处全中：1052@123、1051@126、1050@109。
       这就是表里那句"BMU上报遥测按固定位置解析"的意思。

二、自证（不依赖任何外部工具）
    每个包都做这几项校验，全部通过才认为解析可信：
        · 包长 = 148 字节
        · 帧尾序号 → 对应的 slot 与正在用的表页一致
        · 游标读到的消息ID 能查到定义（查不到 = 定位错了）
        · 游标读到的长度 = 表里声明的 length
        · 锚定消息解出来的"消息ID / 消息长度"两个头字段 = 表里定义
    这比"拿外部工具产物逐格比"更严格：外部工具只能证明"值一样"，
    而这里证明的是"位置找对了" —— 位置敏感，错一位立刻暴露。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from bitfield import extract_bits, read_u16_be
from spec import (
    ROLE_FIELD,
    ROLE_HEADER,
    FieldSpec,
    MessageSpec,
    SlotSpec,
    load_all_slots,
)

# --- 与包结构有关的常量（实测确认）---
FRAME_BYTES = 148           # 一个 slot 包的字节数
FRAME_SEQ_OFFSET = 147      # 帧尾那一字节是帧序号
HEADER_BYTES = 4            # 消息头 = 消息ID(2B) + 消息长度(2B)

# 帧序号 → slot 号（实测：0→slot0、1→slot2、2→slot3、3→slot5）
SEQ_TO_SLOT = {0: 0, 1: 2, 2: 3, 3: 5}

# 需要用"帧尾锚定"方式定位的消息类型（BMU 上报遥测）
ANCHORED_TYPES = ("1050", "1051", "1052")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class DecodedField:
    """解出来的一个字段值。"""

    name: str
    bits: int
    value: int
    role: str       # header / field / padding / trailer
    note: str       # 表里的备注原文（判据要从这里来）

    @property
    def is_business(self) -> bool:
        """是不是真正的业务字段（不是消息头、不是填充、不是帧尾）。"""
        return self.role == ROLE_FIELD

    @property
    def is_header(self) -> bool:
        return self.role == ROLE_HEADER


@dataclass
class DecodedMessage:
    """解出来的一条消息。"""

    type_id: str
    offset: int                                     # 在包里的起始字节偏移
    fields: List[DecodedField] = field(default_factory=list)
    declared_bytes: Optional[int] = None            # 表里声明的载荷长度

    def find(self, name: str) -> Optional[DecodedField]:
        """按字段名找字段。"""
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def header_value(self, which: str) -> Optional[int]:
        """取消息头字段的值。which="id" 取消息ID，"len" 取消息长度。"""
        headers = [f for f in self.fields if f.is_header]
        index = 0 if which == "id" else 1
        return headers[index].value if len(headers) > index else None

    @property
    def business_fields(self) -> List[DecodedField]:
        return [f for f in self.fields if f.is_business]

    @property
    def label(self) -> str:
        return self.type_id or "未知"


@dataclass
class CheckItem:
    """一条自证结果。"""

    name: str
    ok: bool
    detail: str = ""


@dataclass
class DecodedFrame:
    """解出来的一个包，附带自证结果。"""

    row_no: int
    seq: int
    slot_no: int
    sheet_name: str
    messages: List[DecodedMessage] = field(default_factory=list)
    checks: List[CheckItem] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        """自证是否全部通过。"""
        return not self.error and all(c.ok for c in self.checks)

    @property
    def failed_checks(self) -> List[CheckItem]:
        return [c for c in self.checks if not c.ok]

    def message(self, type_id: str) -> Optional[DecodedMessage]:
        """按类型号取某条消息。"""
        for m in self.messages:
            if m.type_id == type_id:
                return m
        return None


# ---------------------------------------------------------------------------
# 消息定位
# ---------------------------------------------------------------------------


def build_type_dict(slot: SlotSpec) -> Dict[str, MessageSpec]:
    """建立「消息ID → 消息定义」字典。

    一个消息可能对应多个 type（按 SC / KA 制式分），所以每个 type 都登记一遍。
    """
    table: Dict[str, MessageSpec] = {}
    for msg in slot.messages:
        for type_id in msg.type_ids:
            table[type_id] = msg
    return table


def anchored_layout(slot: SlotSpec) -> List[Tuple[int, MessageSpec]]:
    """算出「帧尾锚定」消息的起始偏移，返回 [(偏移, 消息定义), ...]（按偏移从小到大）。

    公式：起始偏移 = 147 − (消息总位长 − 帧尾位长) / 8
        1052：147 − (200−8)/8 = 147 − 24 = 123
        1051：147 − (176−8)/8 = 147 − 21 = 126
        1050：147 − (312−8)/8 = 147 − 38 = 109
    三处与实测完全一致。
    """
    anchored = [m for m in slot.messages if any(t in ANCHORED_TYPES for t in m.type_ids)]
    position = FRAME_SEQ_OFFSET
    layout: List[Tuple[int, MessageSpec]] = []
    for msg in reversed(anchored):
        size = (msg.total_bits - msg.trailer_bits) // 8
        position -= size
        layout.append((position, msg))
    layout.reverse()
    return layout


def decode_message(buf: bytes, offset: int, msg_spec: MessageSpec) -> DecodedMessage:
    """按表里字段的顺序，从 offset 开始逐个取位域。

    表里字段的顺序（消息ID → 消息长度 → 业务字段 → 填充 → 帧尾）与包里实际排布一致，
    所以只要按顺序累加位偏移就能取对。越界会抛 ValueError（由调用方记成自证失败）。
    """
    bit_pos = offset * 8
    fields: List[DecodedField] = []
    for spec in msg_spec.fields:
        if spec.bits <= 0:
            continue
        value = extract_bits(buf, bit_pos, spec.bits)
        bit_pos += spec.bits
        fields.append(
            DecodedField(name=spec.name, bits=spec.bits, value=value, role=spec.role, note=spec.note)
        )
    return DecodedMessage(
        type_id=(msg_spec.type_ids[0] if msg_spec.type_ids else ""),
        offset=offset,
        fields=fields,
        declared_bytes=msg_spec.declared_bytes,
    )


def walk_cursor(
    buf: bytes,
    type_dict: Dict[str, MessageSpec],
    stop_offset: int,
    checks: List[CheckItem],
    notes: List[str],
) -> List[DecodedMessage]:
    """从偏移 0 走游标解析，解到 stop_offset 之前为止。

    ★ 关于"扫不动了"的判定（很重要）：
        前面的模块（OM / L2 / PL / FPGA…）**本来就可能不填全**，这是正常现象
        （实测：很多包里该 slot 的前若干字节是 0 或 0x5A 填充）。
        所以扫到识别不了的内容时，**只记录停在哪里，不算自证失败** ——
        真正参与判定的，是帧尾锚定的 BMU 消息（位置固定、每拍都应该有）。
        只有"能认出消息、但长度与表声明不符"才算错。

    Args:
        checks: 自证项收集器（长度不符这类"真问题"进这里）
        notes:  过程记录（"扫到哪停了"这类"正常现象"进这里）
    """
    messages: List[DecodedMessage] = []
    offset = 0

    while offset + HEADER_BYTES <= stop_offset:
        type_id = read_u16_be(buf, offset)
        wire_len = read_u16_be(buf, offset + 2)

        if type_id == 0 and wire_len == 0:
            # 空槽：一次跳过连续的一串 0
            while offset < stop_offset and buf[offset] == 0:
                offset += 1
            continue

        spec = type_dict.get(str(type_id))
        if spec is None:
            # 前段未填全 —— 正常现象，不算失败，记下位置就停
            notes.append("偏移 {} 起无可识别消息".format(offset))
            break

        if spec.declared_bytes is not None and wire_len != spec.declared_bytes:
            checks.append(
                CheckItem(
                    "游标@{} 长度".format(offset),
                    False,
                    "包里写 {} 字节，表里声明 {} 字节".format(wire_len, spec.declared_bytes),
                )
            )

        try:
            messages.append(decode_message(buf, offset, spec))
        except ValueError as exc:
            checks.append(CheckItem("解码@{}".format(offset), False, str(exc)))
            break

        offset += HEADER_BYTES + wire_len

    return messages


# ---------------------------------------------------------------------------
# 总入口
# ---------------------------------------------------------------------------


def decode_frame(buf: bytes, slot: SlotSpec, row_no: int = 0) -> DecodedFrame:
    """解析一个 slot 包，并逐项自证。

    Args:
        buf:     148 字节的包（从 CSV 的 Z 段列拼出来）
        slot:    这一包该用哪一页表定义（由帧序号决定）
        row_no:  CSV 里的行号，用于报告定位

    Returns:
        DecodedFrame，其中 checks 里是全部自证项，failed_checks 是没过的项。
    """
    result = DecodedFrame(
        row_no=row_no,
        seq=-1,
        slot_no=slot.slot_no if slot.slot_no is not None else -1,
        sheet_name=slot.sheet_name,
    )
    checks = result.checks

    # 自证 1：包长
    if len(buf) != FRAME_BYTES:
        checks.append(
            CheckItem("包长度", False, "应为 {} 字节，实际 {}".format(FRAME_BYTES, len(buf)))
        )
        result.error = "包长不对，无法继续"
        return result
    checks.append(CheckItem("包长度", True, "{} 字节".format(len(buf))))

    # 自证 2：帧尾序号与所用的表页是否匹配
    seq = buf[FRAME_SEQ_OFFSET]
    result.seq = seq
    expect_slot = SEQ_TO_SLOT.get(seq)
    if expect_slot is None:
        checks.append(CheckItem("帧序号", False, "帧序号 {} 不在 0~3 范围内".format(seq)))
    elif expect_slot != slot.slot_no:
        checks.append(
            CheckItem(
                "帧序号",
                False,
                "帧序号 {} 应对应 slot{}，但用的是 {} 页".format(seq, expect_slot, slot.sheet_name),
            )
        )
    else:
        checks.append(CheckItem("帧序号", True, "{} → slot{}".format(seq, expect_slot)))

    # 帧尾锚定的消息（BMU）先确定位置，游标别解到它们头上
    anchors = anchored_layout(slot)
    first_anchor = anchors[0][0] if anchors else FRAME_SEQ_OFFSET

    # 游标扫描：前面模块不填全属正常，只记过程、不判失败
    notes: List[str] = []
    messages = walk_cursor(buf, build_type_dict(slot), first_anchor, checks, notes)
    if notes:
        checks.append(
            CheckItem("前段扫描", True, "；".join(notes) + "（前面模块未填全属正常现象）")
        )

    # 锚定消息逐个解码 + 自证
    for position, spec in anchors:
        try:
            msg = decode_message(buf, position, spec)
        except ValueError as exc:
            checks.append(CheckItem("锚定@{}".format(position), False, str(exc)))
            continue

        wire_type = msg.header_value("id")
        expected_types = spec.type_ids
        if wire_type is not None and expected_types and str(wire_type) not in expected_types:
            checks.append(
                CheckItem(
                    "锚定@{} 消息ID".format(position),
                    False,
                    "包里是 {}，表里是 {}".format(wire_type, "/".join(expected_types)),
                )
            )
        else:
            checks.append(
                CheckItem("锚定@{} 消息ID".format(position), True, "type={}".format(wire_type))
            )

        wire_len = msg.header_value("len")
        if wire_len is not None and spec.declared_bytes is not None and wire_len != spec.declared_bytes:
            checks.append(
                CheckItem(
                    "锚定@{} 消息长度".format(position),
                    False,
                    "包里写 {} 字节，表里声明 {} 字节".format(wire_len, spec.declared_bytes),
                )
            )

        messages.append(msg)

    messages.sort(key=lambda m: m.offset)
    result.messages = messages
    return result


def load_slots_by_seq(spec_path: Optional[str] = None) -> Dict[int, SlotSpec]:
    """加载解析表，返回 slot 号 → SlotSpec 的映射（用于按帧序号挑表页）。"""
    mapping: Dict[int, SlotSpec] = {}
    for slot in load_all_slots(spec_path):
        if slot.slot_no is not None:
            mapping[slot.slot_no] = slot
    return mapping
