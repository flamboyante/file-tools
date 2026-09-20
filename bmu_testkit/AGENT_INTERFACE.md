# bmu_testkit — 上位机测试接口契约（给 MCU 侧 agent）

> 这份文档是**自包含**的：拿到它的 agent 无需任何会话上下文即可使用本接口。
> 最后更新：2026-09-20　上位机工程：`C:\heike\md\pythonProjectV3.3.0_beta`
> 状态标注约定：**[已确认]** = 实测或代码算证；**[待确认]** = 推测，使用前需核实。

---

## 0. 一句话

`bmu_testkit` 是**上位机侧**的收发基础设施：能打开 CAN A/B、BMU debug UART、self 422、SC 422 四个通道，发任意字节、收任意字节，并给出耗时统计。它**不关心业务语义** —— 发什么、期望回什么，由调用方（你）决定。

**串口收发默认镜像**：每一次收发都会同步写入日志文件并广播到本地 UDP 端口，
供人用监视窗口实时观察 agent 在串口上做了什么（见 §10）。**不需要任何额外代码，
默认开启**；用 `--no-mirror` 关闭。

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

# 观测层（可选）：让人能在另一个窗口实时看到这次收发（见 §4.5）
from bmu_testkit.mirror import attach_mirror
t = attach_mirror(t)                    # 接口与原来完全一致
```

### 2.2 CLI（副，给人用 / shell 组合）

```bash
cd C:\heike\md\pythonProjectV3.3.0_beta
set PY=C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe

%PY% -m bmu_testkit.cli scan                                     # 列串口
%PY% -m bmu_testkit.cli raw   --preset self --port COM10 --hex "EB 90 ..."
%PY% -m bmu_testkit.cli raw   --port COM2 --recv-only             # 只收不发
%PY% -m bmu_testkit.cli heart --preset self --port COM10 --count 3

%PY% -m bmu_testkit.watch_serial                                  # 另开一窗看实时流量
```

`--preset` = `debug`(115200 8N1) / `self`(921600 8O1) / `sc`(921600 8O1)。
`--timeout` 默认 **None（不超时）**，只记录耗时；要加上限传秒数。

**串口子命令默认开启镜像**（日志 + UDP 广播）。相关开关：

| 参数 | 说明 |
|---|---|
| `--no-mirror` | 关闭镜像 |
| `--mirror-port N` | 指定镜像 UDP 端口，默认 `39527` |

> 日志与 UDP 各自独立：窗口没开也不影响 agent 跑，日志文件照样完整。

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
mirror       —— 观测层：包在 L1 外面，把收发投递给 sink（不参与协议）
```

**换协议 = 只改 L2，L1 不动。** 如果你要发的不是 422 帧，直接用 L1 `write()` 发原始字节即可，不需要动 L2。

`mirror` 是**旁路**：包装 `Transport`，不改任何行为，sink 出错也不影响通信。
它只依赖 `write()` / `read_some()` 两个出口（`read_exact` 等在基类里由 `read_some` 拼装），
因此**包一层即覆盖全部收发路径**。

---

## 4.5 观测层（mirror）：agent 操作时人怎么实时看

**背景**：串口在操作系统层面是**独占**的，同一时刻只能被一个进程打开。
所以人不能"自己再开一个串口看"，正确做法是**持有串口的进程把收发抄一份出来**。

**架构**（两个进程，互不干扰）：

```
agent 进程（你）                     人
  SerialTransport ─ 真的开 COM10
        ↑
  MirroredTransport ─ 每收每发抄一份
        ├─→ 日志文件（完整，事后可查）
        └─→ UDP 39527 ─────────→ watch_serial 窗口（实时）
                                  └─ 不打开串口，只监听端口
```

**默认开启**：任何 `bmu_testkit.cli` 命令都会自动镜像，不需要额外参数。
启动时会打印日志路径和窗口命令：

```
==========================================================
[镜像] 完整日志: ...\bmu_testkit\logs\serial_trace_20260920_013503.log
[镜像] 实时观察: python -m bmu_testkit.watch_serial --port 39527
==========================================================
```

**人的用法**（两条命令，两个终端）：

```bash
# 终端 1：先开窗口，一直开着（谁跑看谁）
python -m bmu_testkit.watch_serial

# 终端 2：agent 跑任意操作
python -m bmu_testkit.cli heart --preset self --port COM10
```

**Python API 用法**（自己写脚本时显式挂载）：

```python
from bmu_testkit.mirror import attach_mirror
from bmu_testkit.transport import SerialTransport

t = SerialTransport(port="COM10", baudrate=921600, parity="O")
t = attach_mirror(t)            # 返回包装后的通道，接口完全一致
```

**关键性质**：
- 窗口**不打开串口** → 物理上不可能与 agent 抢口
- sink 异常被吞掉 → 观察绝不干扰业务
- sink **延迟到串口打开成功后才创建** → 打不开串口时不留空日志
- 窗口没开也不影响 agent → UDP 包直接丢弃，日志文件照样完整

---

## 4.6 事件格式（JSONL）

日志文件与 UDP 包用**同一份格式**：一行一个 JSON 对象。

```json
{"ts":"01:38:26.408","wall":1789839506.408,"dir":"TX","n":27,
 "hex":"eb 90 01 80 c0 00 00 10 01 55 18 fb 06 ...","src":"self","elapsed":0.001}
```

| 字段 | 含义 |
|---|---|
| `ts` | 本地时间 `HH:MM:SS.mmm` |
| `wall` | Unix 时间戳（秒，带小数） |
| `dir` | `TX`（发往设备）/ `RX`（设备返回） |
| `n` | **实际字节数**（即使窗口截断显示，这里也是真值） |
| `hex` | 原始字节的 HEX（空格分隔，**完整，不截断**） |
| `src` | 通道名（preset 名或串口号） |
| `elapsed` | 本次收发耗时（秒） |
| `note` | 可选，CLI 子命令名 |

反向解析用 `bmu_testkit.mirror.parse_event(line)`。

> **截断只发生在窗口显示层**，日志与 UDP 包里永远是完整字节。

---

## 4.7 监视窗口（watch_serial）

独立 PyQt5 程序，只监听 UDP，**不打开串口**。

```bash
python -m bmu_testkit.watch_serial                       # 默认端口 39527，截断 30 字节，HEX 视图
python -m bmu_testkit.watch_serial --truncate 0          # 0 = 全长显示
python -m bmu_testkit.watch_serial --view ascii          # 文本视图（看日志打印，默认按行组装）
python -m bmu_testkit.watch_serial --view ascii --no-assemble   # 文本视图，但保留切块原样
python -m bmu_testkit.watch_serial --port 39528 --view ascii --title "log port"
```

### 视图选择

窗口默认按 **HEX** 渲染载荷；加 `--view ascii` 或勾选界面上的「文本视图」可切成文本。

| 通道性质 | 建议视图 |
|---|---|
| 二进制协议帧（如 422 / CAN 类帧） | `hex` |
| 纯文本日志（banner / 调试打印） | `ascii` |

界面上的「文本视图」复选框可在运行时随时切换（**只影响之后的新行**，历史行不回溯重绘）。

### 按行组装（ascii 视图默认开启）

串口是**字节流，没有消息边界**：内核按缓冲区状况切块返回，一条日志常被拆成
多次 `read`（实测 BL 日志按 1ms 一块刷出，一句话跨 6 行）。开启组装后，
窗口把字节累积起来、**遇 `\n` 才输出一行**：

```
未组装（默认 4 行）          组装后（1 行）
[BL] heartbeat              [BL] heartbeat at 0x001D -> reply 0x001F
 at 0x001D -
> reply 0x001
F
```

| 行为 | 说明 |
|---|---|
| 触发时机 | 遇 `\n`（兼容 `\r\n`，`\r` 显示为 `.`） |
| 半行兜底 | 静默超过 `ASSEMBLE_FLUSH`（0.3s）仍无换行 → 强制吐出，避免无换行的日志一直不显示 |
| 时间戳 | 取**该行首段**的时间戳与方向 |
| 元信息 | 组装产生的事件带 `assembled: true` |
| 关闭方式 | `--no-assemble`，或取消勾选「按行组装」 |

⚠️ **仅在 ascii 视图有效**：hex 视图看的是协议帧时序，拼行会破坏"一个读取块一行"
的对照关系，故强制关闭。切回 hex 时会自动清空残留缓冲。

### 多窗口（可选）

窗口**一窗一口**：同一个 UDP 端口不能被两个进程同时 `bind`，且**不建议**
为其开启 `SO_REUSEADDR` —— 那会让同机任意进程都能抢绑同一端口，
是端口劫持风险，代价远大于"少开一个窗口"。

需要同时观察两条通道时，让两次 `cli` 广播到**不同端口**，再各开一个窗口：

```bash
# 终端 1：发端 A → 39527
python -m bmu_testkit.cli heart --port COM_A --preset <presetA> --mirror-port 39527
# 终端 2：发端 B → 39528
python -m bmu_testkit.cli raw  --port COM_B --preset <presetB> --mirror-port 39528

# 窗口 A：绑 39527，帧看 HEX
python -m bmu_testkit.watch_serial --port 39527 --view hex   --title "A"
# 窗口 B：绑 39528，日志看 ASCII
python -m bmu_testkit.watch_serial --port 39528 --view ascii --title "B"
```

> 若两次 `cli` **都发到默认端口**，则一个窗口即可：事件里的 `src` 字段
> （= `--preset` 名或串口号）可区分来源通道，同屏还能看清两条通道的时序关系。

`tools/start_monitor_dual.bat` 是按上述模式写的一键双窗脚本，可作模板按需修改。

**参数**：

| 参数 | 说明 |
|---|---|
| `--port N` | 监听的 UDP 端口，默认 `39527` |
| `--truncate N` | 每行最多显示字节数，`0` = 全长，默认 30 |
| `--view {hex,ascii}` | 载荷渲染方式，默认 `hex` |
| `--assemble` / `--no-assemble` | 按行组装文本（仅 ascii 视图；ascii 下默认开） |
| `--title S` | 窗口标题，用于区分多窗口 |

**显示形态**（每行一次收发）：

```
01:38:26.408  TX →   27B  eb 90 01 80 c0 00 00 10 01 55 18 fb 06 ...   # hex 视图
01:38:26.409  RX ←   13B  1a cf 01 87 c0 01 00 02 01 5a 00 fe 5a
03:12:07.115  RX ←   23B  [BL] boot loader v1.0..                     # ascii 视图
```

| 功能 | 说明 |
|---|---|
| 截断字节 | 每行最多显示多少字节（默认 30，`0` = 全长） |
| 暂停 | 冻结界面刷新（数据继续入队，不丢） |
| 只看异常 | 只显示异常应答（**仅 13 字节结果类应答**的下标 10 为 `0xFF` / `0x11`） |
| 自动滚动 | 滚到底部跟随最新 |
| **文本视图** | 勾选切 ASCII，取消切 HEX（只影响后续新行，历史行不回溯重绘） |
| **按行组装** | 把被切碎的文本拼回整行（仅文本视图；默认开） |
| 清空 | 清掉显示与计数 |

**配色**：`TX` 蓝 / `RX` 绿 / **异常整行红**。
**异常判定口径**：结果码只存在于**数据域 3 字节（总长 13）**的应答里。
判定前先按帧内 `[6:8]` 长度字段算出总长，只有确实是 13 字节才读下标 10；
心跳等 12 字节应答的下标 10 是**校验和高位**，不得当作结果码
（否则校验和恰为 `0xFF` 的正常心跳会被误标红）。
**ASCII 口径**：只放行 ASCII 可见字符（`0x20~0x7E`）与 TAB，其余（含 `\r` `\n`
与 0x80 以上高位字节）一律显示为 `.`。**必须逐字节判定**，不能用
`str.isprintable()` —— 后者经 latin-1 解码会把 `0x80~0xFF` 当成可打印字符，
二进制帧就会显示成 `ÿÏ` 之类乱码字母。
**缓冲上限**：5000 行（超出自动丢弃最旧的）。
**批量刷新**：40ms 合并一次，高频流量下不卡界面。

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

### 已实现（L1/L2/core 均真机验证；观测层见下）

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

**观测层**（`mirror/`，2026-09-20 新增）
- `MirroredTransport`：包装任意 `Transport`，收发投递给 sink，**透传所有行为与异常**
- `FileSink`（JSONL 日志）/ `UdpSink`（本机 UDP 广播）
- `watch_serial.py`：独立 PyQt5 监视窗口，**只监听 UDP、不打开串口**
- 无硬件自测：`transport/fake_transport.py` + `tools/selftest_*.py`（镜像 5 项 / 窗口显示 / 端到端）

**CLI**：`scan` / `raw`（含 `--recv-only`）/ `heart` / `can` / `file-transfer`
（串口子命令默认开镜像，见 §2.2）

### 四条通道验证状态

| 通道 | 端口 | 状态 |
|---|---|---|
| self 422 | 原 COM10 | 心跳 + 文件传输均通过 |
| CAN A / CAN B | USBCAN 卡 | 状态查询通过，`status/rx_err/tx_err` 全 0 |
| debug UART | COM4（115200 8N1） | 字符回显通过 |
| SC 422 | 现 COM10 | 发帧被 MCU 完整接收（debug 口可见转发打印） |

> 注：`COM10` 已被改用为 SC；self 422 通路需把线改回后才能复测。

### 观测层验证状态

| 项 | 状态 |
|---|---|
| 镜像层自测（5 项：透传一致 / 文件 sink / UDP sink / 故障隔离 / 延迟建 sink） | **通过**（无硬件，假串口） |
| 监视窗口显示自测（截断 / 配色 / 异常标红） | **通过**（出预览图） |
| 端到端（真实 `FileTransfer` + 假串口 + 窗口） | **通过**：begin→data→finish→refactor 全流程，2048B / 2 帧传输成功 |
| 真机验证 | ⬜ **未做**（暂无硬件） |
| 真机心跳 + 镜像端到端 | **通过**（2026-09-20，debug 口发心跳，镜像双通道收到 TX 12B / RX 12B 三拍，序号递增） |
| 异常标红判定 | **已修**：原按固定下标 10 判定，会把校验和高位为 `0xFF` 的正常心跳误标红；现改为按 `[6:8]` 算出总长、仅 13 字节应答才判 |
| HEX/ASCII 双视图 | **通过**（`tools/selftest_view.py` 7/7：高位字节→`.` / 可打印保留 / TAB 保留 / `\r`→`.` / hex 方向） |
| 双窗口 / 多端口路由 | **通过**（窗口 `--view` `--title` 参数解析；`cli --mirror-port` → `UdpSink(port=)` 透传；`attach_mirror` 端口路由为参数而非常量） |
| 镜像→UDP 端到端 | **通过**（假串口 `attach_mirror(udp_port=)`，真实 UDP 收包 2/2，事件 JSON 完整） |
| 读取路径不重配端口 | **通过**（`tools/selftest_serial_read.py` 21/21：读循环期间 `timeout` **零次赋值**，含 10 次连续读验证；`read_exact` / `read_until_idle` 行为不回归） |
| 文本按行组装 | **通过**（`tools/selftest_assemble.py` 23/23：真机碎片 4 块→1 行、跨刷新半行保留、超时兜底、混合场景、元信息取首段） |

> 真机验证方法（接线就绪后）：
> ```bash
> python -m bmu_testkit.watch_serial                                   # 终端 1
> python -m bmu_testkit.cli heart --preset self --port <self422口> --count 3   # 终端 2
> ```
> 预期：窗口里看到 `EB 90 ... 00 1D` 出去、`1A CF ... 00 1F` 回来。

> **窗口进程必须由人启动**：agent 沙箱会回收 agent 拉起的 GUI 进程（`pythonw` /
> `Popen(DETACHED)` / `cmd start` / `Start-Process` 均被清理，`wmic` 被安全策略硬拦）。
> 因此 agent 只能**准备好启动脚本**，由用户双击：
> `bmu_testkit\tools\start_monitor.bat`（单窗）或 `start_monitor_dual.bat`（双窗）。

### 未实现

1. **GUI 接 core（V2）** —— 当前 GUI 仍是独立的老实现，未使用本包
2. 用例层 `cases/`（按要求不做，本包只提供基础设施）
3. SC 反向（MCU → 上位机）未验证
4. 监视窗口**发帧**（当前只读观察；窗口内手动发帧需要与 agent 的串口写做互斥，未做）

---

## 9. 硬约束

1. **core 层不许 import PyQt5**（CLI/GUI 共用同一 core，破了这条 V2 GUI 就废）
   - 观测层同理：**CLI 不引入 Qt 依赖**。窗口是**独立程序**（`watch_serial.py`），
     由人单独启动，不由 CLI 拉起 —— 这样没装 PyQt5 的机器照样能跑 CLI。
2. **默认不超时**（阻塞等待），只记耗时 —— 需要上限显式传 `--timeout` / `timeout=`
3. **串口号变化频繁**，不做自动识别，由调用方指定
4. 文件传输是**危险操作**：会真实擦除 Flash 分区，中断会留下空白分区 → 必须二次确认，且不允许中途打断
5. **文件传输期间不得有后台流量**（心跳 / 保活 / 周期消息一律不发）。串口上只应有传输帧。
6. **观测不得干扰业务**：镜像层的 sink 异常一律吞掉；sink 延迟到串口打开成功后才创建。
7. **传输实现打开端口后不得修改通信参数**（尤其 `timeout`）。
   pyserial 的 `SerialBase.timeout` setter 在 `is_open` 为真时会调用
   `_reconfigure_port()`；Windows 上它会对已打开的句柄重新 `SetCommState`。
   后果有二：设备被拔掉 / 复位重枚举时抛
   `SerialException: PermissionError(13, ...)`；设备健在时则每次循环都引入一次
   内核态重配，**污染本包本要观测的真实时序**。
   → 本包的做法：内核读超时固定为 `_READ_TIMEOUT`（仅 `open()` 前设定），
   上层超时由 `read_some` 自行计时。
   → 新增传输实现时请沿用此约定，并跑 `tools/selftest_serial_read.py` 验证
   "读循环期间 timeout 零次赋值"。

> ⚠️ 第 5 条的现实风险：工程里老 GUI 的 `Serial_thread.py` 带着**两个 3 秒周期的后台定时器** ——
> `heart_timer`（其槽函数 `check_heart` 目前是空的）和 `fixed_message_timer`
> （`send_fixed_background_message()` **会真的往串口发** `FIXED_BACKGROUND_PAYLOAD`）。
>
> **将来 GUI 接 core 时，不要把这两个定时器一起带过来** —— 否则文件传输期间会掺入无关帧。
>
> 本包**不含任何自动心跳**：`heart` 只是手动 CLI 命令，`build_heartbeat()` 只是组帧函数，
> `filetransfer.py` 里没有任何周期性发送。

---

## 10. 目录结构

```
bmu_testkit/
├── AGENT_INTERFACE.md      本文件
├── cli.py                  命令行入口（默认开镜像）
├── watch_serial.py         监视窗口（独立程序，只监听 UDP）
├── transport/              L1：只搬 bytes
│   ├── base.py             Transport 抽象 + read_exact / read_until_idle + WaitStats
│   ├── serial_transport.py 串口实现
│   ├── can_transport.py    CAN 实现
│   └── fake_transport.py   假串口（无硬件自测）
├── protocol/               L2：422 组帧与解析
│   └── ycyk422.py          帧长计算 / read_frame / decode_response
├── core/                   业务流程
│   ├── filetransfer.py     文件传输全流程
│   └── console.py          文本流判据
├── mirror/                 观测层（2026-09-20 新增）
│   ├── transport.py        MirroredTransport + attach_mirror
│   └── sinks.py            FileSink / UdpSink / JSONL 事件格式
├── tools/                  自测脚本与启动脚本
│   ├── selftest_mirror.py  镜像层自测（5 项）
│   ├── selftest_window.py  窗口显示自测（出预览图）
│   ├── selftest_e2e.py     端到端（真实 FileTransfer + 窗口）
│   ├── selftest_view.py    HEX/ASCII 双视图渲染自测（7 项，无需 GUI/硬件）
│   ├── selftest_assemble.py 文本按行组装自测（23 项，含真机碎片复现）
│   ├── selftest_serial_read.py  串口读取路径自测（21 项：timeout 零赋值等）
│   ├── start_monitor.bat   单窗启动（双击用，参数透传）
│   ├── start_monitor_dual.bat  双窗启动（HEX + ASCII 各一窗）
│   └── start_monitor_dual.py   双窗启动（逐个拉起并校验端口）
└── logs/                   镜像日志（每次运行新文件，不入版本控制）
```

自测命令（无需硬件）：

```bash
python -m bmu_testkit.tools.selftest_mirror    # 镜像层
python -m bmu_testkit.tools.selftest_window    # 窗口显示
python -m bmu_testkit.tools.selftest_e2e       # 端到端全流程
```
