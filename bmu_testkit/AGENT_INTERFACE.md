# bmu_testkit — 上位机测试接口契约（给 MCU 侧 agent）

> 这份文档是**自包含**的：拿到它的 agent 无需任何会话上下文即可使用本接口。
> 最后更新：2026-09-17　上位机工程：`C:\heike\md\pythonProjectV3.3.0_beta`
> 状态标注约定：**[已确认]** = 实测或代码算证；**[待确认]** = 推测，使用前需核实。

---

## 0. 一句话

`bmu_testkit` 是**上位机侧**的收发基础设施：能打开 CAN A/B、BMU debug UART、self 422、SC 422 四个通道，发任意字节、收任意字节，并给出耗时统计。它**不关心业务语义** —— 发什么、期望回什么，由调用方（你）决定。

---

## 0.5 使用前必读：先自检，再操作

**不要照抄本文档里的串口号** —— 现场经常变。任何实际操作前按顺序走完这三步：

**① 确认当前串口号**
```bash
%PY% -m bmu_testkit.cli scan
```

**② 验证目标通道通路**
```bash
%PY% -m bmu_testkit.cli heart --preset self --port <上一步查到的口>
```
- 预期：12 字节应答，以 `1A CF` 开头，IRCode 位置是 `0x001F`
  实测样本：`1A CF 01 87 C0 00 00 01 00 1F FE 97`
- **收不到 / 开头不是 1A CF / 帧长不对 → 停下来查接线，不要继续**

**③ 通路确认后，才执行写操作**（`file-transfer` 会真实擦除 Flash）

> 在未验证通路的串口上执行写操作是危险的。这三步不是形式，是前置条件。

### 当前硬件接线（可能已变动，以实测为准）

| 目标 | 曾用/现用端口 | 备注 |
|---|---|---|
| self 422 | 原 `COM10` | ⚠️ **该口已改用为 SC**，要测 self 需重新接线 |
| SC 422 | 现 `COM10` | 921600 8O1 |
| debug UART | `COM4` | 115200 8N1，字符交互 |
| CAN A / CAN B | 非串口 | 蒋氏 USBCAN 卡，双通道独立 |

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

## 6. 协议事实（已全部真机实测确认）

**以下不是推测**，是实测结论。改代码时不要凭直觉改动这些常量或偏移。

| 项 | 结论 |
|---|---|
| 请求帧头 | `EB 90` |
| 应答帧头 | **`1A CF`** —— 与请求**不同**，self 422 口固定如此（协议不对称，已实测） |
| 帧长公式 | `[6:8]` 字段值 = **数据域长度 − 1**；总帧长 = `8 + 数据域 + 2` |
| `[8:10]` | IRCode（心跳应答 = `0x001F`） |
| `[9]` | 文件传输类型码：`0x5A` 开始 / `0x8A` 数据 / `0xBB` 结束 / `0xCA` 重构结果 |
| `[10]` | 结果码：`0x00` 成功 / `0xFF` 异常 / `0x11` CRC 异常 |
| 校验和 | 从 index 2 起逐字节累加 → 取反 → `& 0xFFFF`（16 位大端） |

### 帧长公式怎么用（`read_frame()` 靠它做到不预设长度）

| `[6:8]` 值 | 数据域 | 总帧长 | 用途 |
|---|---|---|---|
| 1 | 2 字节 | **12** | 心跳应答（数据域 = 16 位 IRCode） |
| 2 | 3 字节 | **13** | 文件传输应答（数据域 = ? + 类型码 + 结果码） |
| 16 | 17 字节 | **27** | 文件传输 begin 请求帧 |

> 因为长度能算出来，就不需要「先猜长度再超时兜底」—— 这是 `read_frame()` 能通吃任意帧长的原因。

### 实测样本（可直接拿去做单元测试）

| 场景 | 帧 |
|---|---|
| 心跳请求 | `EB 90 01 80 C0 00 00 01 00 1D FE A0`（12B） |
| 心跳应答 | `1A CF 01 87 C0 00 00 01 00 1F FE 97`（12B） |
| 文件传输 begin 请求 | `EB 90 01 80 C0 00 00 10 01 55 18 FB 06 ... FA A6`（27B） |
| begin 应答 | `1A CF 01 87 C0 07 00 02 01 5A 00 FE 53`（13B） |
| finish 应答 | `1A CF 01 87 C0 06 00 02 01 BB 00 FD F3`（13B） |
| CAN 状态查询应答 | `00 2A 00 00 00 5A 5A DE`（8B，含 status/rx_err/tx_err=0） |

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

## 7.5 文件传输（重构升级）怎么用

对外接口**只收「文件路径 + 参数」**，不接收字节流 —— 读文件、分帧、逐帧等应答全部是内部实现。

### Python API（agent 用这个）

```python
from bmu_testkit.transport import SerialTransport
from bmu_testkit.core.filetransfer import FileTransfer

t = SerialTransport(port="COM10", baudrate=921600, bytesize=8,
                    parity="O", stopbits=1, timeout=None)
t.open()
ft = FileTransfer(t, on_log=print,
                  on_progress=lambda sent, total: print(f"{sent}/{total}"))

result = ft.transfer(
    file_path=r"C:\path\to\file.bin",   # 待传文件路径
    flash=0xFB,                          # 目标 Flash（见下方取值说明）
    mem=0x06,                            # 目标分区（见下方取值说明）
    require_confirm=False,               # agent 场景：确认已在对话层完成
    timeout=10,                          # 单步超时（秒）；None = 不超时
)
print(result.ok, result)
t.close()
```

**`flash` / `mem` 取值说明**

这两个是**业务参数**（告诉固件传到哪块 Flash 的哪个分区），本包不做猜测，必须由调用方给定。

| 参数 | 实测自测用过的值 | 说明 |
|---|---|---|
| `flash` | `0xFB` | 实测用它成功完成过完整传输（上位机侧观察） |
| `mem` | `0x06` | 同上 |

> ⚠️ **`0xFB` / `0x06` 只是自测验证通路时用过的值，不等于正式业务值**。
> 正式传输请向硬件/业务负责人确认目标分区，**填错会擦错分区**。
> 固件侧相关逻辑见 `check_apid()`（`flash` 参与 apid 计算：`0xFA→0x1D`、`0xFB/0x9b→0x18`）。

### CLI（人敲命令用）

```bash
%PY% -m bmu_testkit.cli file-transfer --preset self --port COM10 ^
      --flash 0xFB --mem 0x06 --timeout 10
```
`--file` 省略时自动挑工程内的小文本文件；`--yes` 跳过二次确认（仅在确认已在上层完成时用）。

### 流程与判据

```
begin    → 等 0x5A      失败：抛 FileTransferError，或超时
每帧数据 → 等 0x8A      ← 严格每帧等待，没有开关可关
finish   → 等 0xBB      ← 收到即判成功
refactor → 发起重构，不等结果
```

`TransferResult` 字段：`ok / path / file_size / frames_sent / bytes_sent / elapsed_s / stage / error / last_response_hex`。
**失败时先看 `stage`（卡在哪一步）和 `last_response_hex`（最后收到的原始帧）。**

### 危险须知

- **会真实擦除目标 Flash 分区**，中断会留下空白分区
- 默认二次确认；agent 场景由对话层确认后传 `require_confirm=False`
- 传输进行中**忽略 Ctrl+C**（SIGINT 保护），避免半途而废
- **不需要、也不应该有心跳**：传输期间串口上只应有传输帧（见 §9）

---

## 8. 已实现 / 未实现

### 已实现（均真机验证）

**L1 传输**
- `SerialTransport`：任意字节流、超时可配、静默判定、耗时统计
- `CanMedia`：CAN 帧级接口（`send_frame`/`recv_frame`）+ 字节流适配
  - ⚠️ 底层 `Transmit` 在总线异常时会**永久阻塞**，已用线程 + 超时兜底

**L2 协议**（`protocol/ycyk422.py`）
- 422 组帧复用工程现有 `ycyk_422.Ycyk_422_Work`，不重写
- 帧长按 `[6:8]` 长度字段计算 → `read_frame()` 通吃任意帧长
- 严格断言解析 + 校验和验证

**core**
- `FileTransfer`：文件传输全流程（每帧等应答 / 二次确认 / SIGINT 保护）
- `Console`：通用文本流判据（`wait_for` / `wait_for_any` / `wait_for_sequence` / `wait_silent`），**游标只前进，不会命中旧打印**

**CLI**：`scan` / `raw`（含 `--recv-only`）/ `heart` / `can` / `file-transfer`

### 四条通道验证状态

| 通道 | 端口 | 状态 |
|---|---|---|
| self 422 | 原 COM10 | 心跳 + 文件传输均通过 |
| CAN A / CAN B | USBCAN 卡 | 状态查询通过，`status/rx_err/tx_err` 全 0 |
| debug UART | COM4（115200 8N1） | 字符回显通过 |
| SC 422 | 现 COM10 | 发帧被 MCU 完整接收（debug 口可见转发打印） |

> 注：`COM10` 已被改用为 SC；self 422 通路需把线改回后才能复测。

### 未实现

1. **GUI 接 core（V2）** —— 当前 GUI 仍是独立的老实现，未使用本包
2. 用例层 `cases/`（按要求不做，本包只提供基础设施）
3. SC 反向（MCU → 上位机）未验证

---

## 9. 硬约束

1. **core 层不许 import PyQt5**（CLI/GUI 共用同一 core，破了这条 V2 GUI 就废）
2. **默认不超时**（阻塞等待），只记耗时 —— 需要上限显式传 `--timeout` / `timeout=`
3. **串口号变化频繁**，不做自动识别，由调用方指定
4. 文件传输是**危险操作**：会真实擦除 Flash 分区，中断会留下空白分区 → 必须二次确认，且不允许中途打断
5. **文件传输期间不得有后台流量**（心跳 / 保活 / 周期消息一律不发）。串口上只应有传输帧。

> ⚠️ 第 5 条的现实风险：工程里老 GUI 的 `Serial_thread.py` 带着**两个 3 秒周期的后台定时器** ——
> `heart_timer`（其槽函数 `check_heart` 目前是空的）和 `fixed_message_timer`
> （`send_fixed_background_message()` **会真的往串口发** `FIXED_BACKGROUND_PAYLOAD`）。
>
> **将来 GUI 接 core 时，不要把这两个定时器一起带过来** —— 否则文件传输期间会掺入无关帧。
>
> 本包**不含任何自动心跳**：`heart` 只是手动 CLI 命令，`build_heartbeat()` 只是组帧函数，
> `filetransfer.py` 里没有任何周期性发送。
