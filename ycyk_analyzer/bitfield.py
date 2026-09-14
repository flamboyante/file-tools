# -*- coding: utf-8 -*-
"""
bitfield.py —— 位域解码：把一串字节按"高位先"拆成一个个数值。

为什么单独搞一个文件：
    位序这种东西搞错了，所有数值都会错，而且错得很隐蔽 —— 不会报错，只会算错。
    所以把它隔离开，只做一件事：从字节流里取一段二进制位，转成整数。
    **越界直接抛错，绝不静默返回 0 或垃圾值**（外部工具就是静默填了 240 / 255 这种假值）。

本项目的位序约定（已由实测确认）：
    高位先（MSB-first）—— 一个字节里，最左边（最高位）先算。

    例：字节 0x03, 0xF2 拼成 16 位，值是 0x03F2 = 1010
        这是慢遥 slot2 包里第一条消息的"消息ID"，实测正好是 1010，对得上。
"""

from __future__ import annotations


def extract_bits(data: bytes, bit_offset: int, bit_len: int) -> int:
    """从 data 的第 bit_offset 位开始，取 bit_len 位，按"高位先"拼成整数。

    Args:
        data:       字节串（比如一个 148 字节的 slot 包）
        bit_offset: 从第几位开始算（0 = 最前面那个字节的最高位）
        bit_len:    取多少位

    Returns:
        取出来的无符号整数

    Raises:
        ValueError: 参数不合法或越界 —— 故意抛错，不静默
    """
    if bit_len <= 0:
        raise ValueError("bit_len 必须是正数，收到 {}".format(bit_len))
    if bit_offset < 0:
        raise ValueError("bit_offset 不能是负数，收到 {}".format(bit_offset))

    total_bits = len(data) * 8
    if bit_offset + bit_len > total_bits:
        raise ValueError(
            "越界：想要第 {}~{} 位，但数据只有 {} 位（{} 字节）".format(
                bit_offset, bit_offset + bit_len - 1, total_bits, len(data)
            )
        )

    value = 0
    for i in range(bit_len):
        pos = bit_offset + i
        byte_index = pos // 8
        # 高位先：一个字节里，"第 0 位"指的是最高位（bit7）
        bit_index = 7 - (pos % 8)
        bit = (data[byte_index] >> bit_index) & 1
        value = (value << 1) | bit
    return value


def read_u16_be(data: bytes, byte_offset: int) -> int:
    """读 2 字节的"大端"整数（等价于 extract_bits(data, byte_offset*8, 16)）。

    单独写一个，是为了让"读消息头"的代码读起来更直观。
    """
    return extract_bits(data, byte_offset * 8, 16)


def to_hex(data: bytes) -> str:
    """把字节串转成空格分开的十六进制，调试时方便看。"""
    return " ".join("{:02X}".format(b) for b in data)
