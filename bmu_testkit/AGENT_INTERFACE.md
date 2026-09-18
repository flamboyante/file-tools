# bmu_testkit — 上位机测试接口契约（给 MCU 侧 agent）

> 这份文档是**自包含**的：拿到它的 agent 无需任何会话上下文即可使用本接口。
> 最后更新：2026-09-17　上位机工程：`C:\heike\md\pythonProjectV3.3.0_beta`
> 状态标注约定：**[已确认]** = 实测或代码算证；**[待确认]** = 推测，使用前需核实。

---

## 0. 一句话

`bmu_testkit` 是**上位机侧**的收发基础设施：能打开 CAN A/B、BMU debug UART、self 422、SC 422 四个通道，发任意字节、收任意字节，并给出耗时统计。它**不关心业务语义** —— 发什么、期望回什么，由调用方（你）决定。

---

## 1. 运行环境 [已确认]

```
Python:   C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe   (3.8.18)
依赖:     pyserial 3.5、PyQt5（本包不用 Qt，但工程其他部分用）
工作目录: C:\heike\md\pythonProjectV3.3.0_beta
```

本包**零 Qt 依赖**，headless 可跑，不需要启动 GUI。

---

## 2. 两套入口

### 2.1 Python API（主，推荐）

```python
import sys
sys.path.insert(0, r"C:\heike\md\pythonProjectV3.3.0_beta")

from bmu_testkit.transport import SerialTransport
from bmu_testkit.protocol import Ycyk422Protocol

# L1：通用传输，发任意字节流
t = SerialTransport(port="COM10", baudrate=921600, bytesize=8,
                    parity="O", stopbits=1, timeout=None)
t.open()
t.write(bytes.fromhex("EB900180C0000001001DFEA0"))
resp = t.read_until_idle(idle=0.3)      # 未知应答长度时用这个
# 或 resp = t.read_exact(13, timeout=3)  # 已知长度用这个
print(resp.hex(" "), t.stats.as_dict())
t.close()

# L2：422 指令组帧（当前协议）
p = Ycyk422Protocol()
frame = p.build_heartbeat()             # 心跳帧
info  = p.decode_response(resp)         # 宽松解析（见 §5）
```

### 2.2 CLI（副，给人用 / shell 组合）

```bash
cd C:\heike\md\pythonProjectV3.3.0_beta
set PY=C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe

%PY% -m bmu_testkit.cli scan                                     # 列串口
%PY% -m bmu_testkit.cli raw   --preset self --port COM10 --hex "EB 90 ..."
%PY% -m bmu_testkit.cli raw   --port COM2 --recv-only             # 只收不发
%PY% -m bmu_testkit.cli heart --preset self --port COM10 --count 3
```

`--preset` = `debug`(115200 8N1) / `self`(921600 8O1) / `sc`(921600 8O1)。
`--timeout` 默认 **None（不超时）**，只记录耗时；要加上限传秒数。

---

## 3. 通道参数 [已确认]

| 通道 | 波特率 | 数据位 | 校验 | 停止位 | preset |
|---|---|---|---|---|---|
| BMU debug UART | 115200 | 8 | **None** | 1 | `debug` |
| self 422（自主管理） | 921600 | 8 | **Odd** | 1 | `self` |
| SC 422（SC 天线） | 921600 | 8 | **Odd** | 1 | `sc` |
| CAN A / CAN B | 500K | — | — | — | *未实现* |

串口号由调用方指定（现场经常变，不做自动识别）。

---

## 4. 分层（重要）

```
L1 transport —— 只搬运 bytes，不认识任何协议
L2 protocol  —— 422/CAN 组帧与应答解析，是「当前这套指令格式」的唯一实现
```

**换协议 = 只改 L2，L1 不动。** 如果你要发的不是 422 帧，直接用 L1 `write()` 发原始字节即可，不需要动 L2。

---

## 5. 现有指令速查 [已确认 · 帧值]

| 指令 | API | 帧（hex） | 发往 |
|---|---|---|---|
| 心跳 `0x001D` | `build_heartbeat()` | `EB 90 01 80 C0 00 00 01 00 1D FE A0` | self 422 |
| 软复位 `0x001A` | `build_reboot()` | 由 `Send_Reboot()` 生成 | self 422 |
| 版本查询 `0x0101` | `build_version_check()` | 由 `Send_VersionCheck()` 生成 | self 422 |

心跳帧结构：`EB 90`=id / `01 80`=apid `0x18` / `C0 00`=控制+序列 / `00 01`=数据域长度 / `00 1D`=IRCode / `FE A0`=校验和。
**校验算法**：从 **index 2** 起逐字节累加 → 取反 → `& 0xFFFF`（16 位大端）。改帧必须重算。

---

## 6. 应答解析：当前是宽松的，请你来收紧  **[待确认]**

`decode_response()` 现在**不做硬断言**，而是把几个候选位置一起返回：

```
ircode_at_8   : resp[8:10] 组成的 16 位值   （与心跳帧 IRCode 位置一致）
type_at_9     : resp[9]                      （与文件传输应答类型码位置一致）
type_label    : 0x5A 开始 / 0x8A 数据 / 0xBB 结束 / 0xCA 重构结果
result_at_10  : resp[10] → 0x00 成功 / 0xFF 异常 / 0x11 CRC 异常
```

**我不知道应答帧的真实布局。** 这是当前最大的不确定性。

> ### 👉 给 MCU 侧 agent 的请求
> 你有固件源码，请直接从下位机侧读出并告诉我：
> 1. 心跳（`0x001D`）的应答帧**确切字节序列**与每个字段的偏移
> 2. 文件传输应答（类型码 `0x5A/0x8A/0xBB/0xCA`）帧长是否固定 **13** 字节，字段偏移是否 `[9]`=类型、`[10]`=结果
> 3. 校验和算法是否与上位机一致（index 2 起累加取反）
>
> 拿到这三条，我把 `decode_response()` 从"猜"改成"断言"，后续所有判据才有意义。
> 若不方便读源码，退而求其次：给我一次真实应答的 hex 也行。

---

## 7. 协作契约（联合测试怎么跑）

**你给我**：
1. 目标通道（debug / self / sc / can-a / can-b）
2. 要发的完整帧（hex），或调用哪个 `build_*()`
3. 期望判据：等到什么算通过（关键字 / 字节偏移+值 / 超时）
4. 是否需要「发完等应答」

**我给你**：
1. 实际发出的帧 hex
2. 实际收到的完整 hex
3. 耗时（单次 + 累计统计：次数/总计/最长/均值）
4. 解析结果，或明确的失败上下文（超时异常带已收字节与耗时）

---

## 8. 已实现 / 未实现

**已实现**
- L1 串口传输（任意字节、超时可配、静默判定、耗时统计）
- L2 422 组帧（心跳 / 复位 / 版本查询）+ 宽松应答解析
- CLI：`scan` / `raw`（含 `--recv-only`）/ `heart`
- 超时异常携带 partial + elapsed（便于现场排查）

**未实现**（按优先级）
1. CAN A/B transport（计划用 `JiangCan_Tools/ECAN.py`，ctypes 调 `ECanVci64.dll`）
2. 文件传输状态机（`begin`→`0x5A` / 每帧→`0x8A` / `finish`→`0xBB` / `refactor`→`0xCA`，**每帧都要等应答**）
3. `console` 游标匹配（debug 口打印的「关键字包含 + 时序游标」判据机制）
4. 用例层 `cases/`（明确不做，本包只提供基础设施）

---

## 9. 硬约束

1. **core 层不许 import PyQt5**（CLI/GUI 共用同一 core，破了这条 V2 GUI 就废）
2. **默认不超时**（阻塞等待），只记耗时 —— 需要上限显式传 `--timeout` / `timeout=`
3. **串口号变化频繁**，不做自动识别，由调用方指定
4. 文件传输是**危险操作**：会真实擦除 Flash 分区，中断会留下空白分区 → 必须二次确认，且不允许中途打断
