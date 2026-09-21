# gui-ng · 新 UI 骨架

上位机（JiangCan Tools）新一代界面层。目标是**取代旧 `UIClass/` 那批窗口**，
把串口/CAN 收发、固件传输、调试指令统一到一套分层与一套视觉上。

- 分支：`feat/gui-ng`（worktree `C:\heike\uicmp`，与主工作区分离，互不干扰）
- 运行环境：`C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe`（Python 3.8.18 + PyQt5 5.15.10 + PyQt-Fluent-Widgets 1.11.3）
- 入口：`python FileFIle.py` → 命令栏「UI 方案对比 / dev_launcher」→ 四张卡

---

## 1. 当前状态

| 页面 | app | 会话层 | 功能 | 视觉 | 真机 |
|---|---|---|---|---|---|
| 控制台 | `apps/console_app.py` | `guicore/console_session.py` | 完成 | 完成 | **未验** |
| 文件传输 | `apps/transfer_app.py` | `guicore/transfer_session.py` + `transfer_queue.py` | 完成 | 完成 | **未验** |
| SC422 收发台 | `apps/sc422_app.py` | `guicore/sc422_session.py` | 完成 | 完成 | **未验** |
| CAN | 未开工 | — | ⬜ | ⬜ | ⬜ |

dev_launcher 四张卡：三张已点亮，CAN 待开工。

---

## 2. 分层

```
guiwidgets/
  theme.py            色板 + QSS 工厂（浅/深双套，唯一颜色来源）
  common.py           ConnectionBar（通道配置条 v2）、badge
guicore/       会话层：只管数据与流程，不含 Qt 控件（可单测）
  serial_link.py      链路门面（读线程 + 写队列 + 信号）
  console_session.py  文本命令会话（CR 结尾、历史栈）
  transfer_session.py 422 传输状态机（begin/data/finish）
  transfer_queue.py   批量调度（失败策略/暂停/取消）
  sc422_session.py    原始 hex 收发 + 定时（纯函数：parse_hex / format_ascii）
apps/          页面（只管 UI 与信号连接）
tools/         冒烟 · 出图 · 假设备 · 现场联调脚本
```

**架构判据**：`guicore` 里不许出现 Qt 控件（`QObject`/信号可以）；页面不许直接碰 `serial`。
换 UI 框架时只有 `guiwidgets` + `apps` 重写。

---

## 3. 通道参数（实测，来自 `bmu_testkit/AGENT_INTERFACE.md` §3）

| 通道 | 波特率 | 数据位 | 校验 | 停止位 | 用途 |
|---|---|---|---|---|---|
| BMU debug UART | 115200 | 8 | **None** | 1 | 字符交互（console） |
| self 422 | 921600 | 8 | **Odd** | 1 | 自主管理 422 |
| SC 422 | 921600 | 8 | **Odd** | 1 | 文件传输与 sc422 页默认预设 |
| CAN A / B | 500K | — | — | — | 蒋氏 USBCAN |

ConnectionBar v2 已把这四个固化成**预设**（选预设自动套波特率 + 校验）：

```
预设 [SC 422 ▾]  端口 [COM3 ▾] ⟳  波特率 [921600 ✎]  校验 [奇校验 (O) ▾]  [打开]  [●已连接]
```

- 波特率可**手敲任意值**（EditableComboBox）
- 参数**按页持久化**（`QSettings('JiangCan','gui-ng')`，键 `connbar/<settings_key>`）
- 数据位/停止位不做 UI：三通道都是 8/1；底层 `SerialLink.open()` 已支持透传，需要时再开

---

## 4. 冒烟与出图

### 冒烟（每次改完必跑，全绿才算完成）

```
%PY% tools/smoke_theme.py             # 主题色板 / 卡片底色跟随 / 字体
%PY% tools/smoke_serial_link.py       # 链路：收发 / 异常上报 / 线程退出
%PY% tools/smoke_connection_bar.py    # 预设联动 / 校验位透传 / 持久化 / 状态同步
%PY% tools/smoke_console_app.py       # 命令 CR / 历史 / hex / 提示着色不残留
%PY% tools/smoke_transfer_session.py  # 422 状态机（假设备应答器）
%PY% tools/smoke_transfer_queue.py    # 批量调度 / 失败策略 / 暂停取消
%PY% tools/smoke_sc422.py             # hex 解析 / 定时 / 视图口径 / UI
```

`%PY%` = `C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe`

### 出图（改动视觉后跑，产物在 `docs/gui_ng/`）

```
%PY% tools/shot_states.py        # transfer 页面：五状态 + 已连接态（浅/深）
%PY% tools/shot_console.py       # console 页（浅/深）
%PY% tools/shot_sc422.py         # sc422 页（模拟心跳问答）
%PY% tools/shot_transfer_compare.py  # 新旧批量窗口对比
%PY% tools/shot_button_colors.py     # 按钮配色候选（选型用）
```

**出图两条铁律**（都是实测踩出来的）：

1. **offscreen 下必须等入场动画**（`settle(700ms)`）再 `grab()`，否则 qfluentwidgets 控件
   会从截图里凭空消失——看着像 bug，其实是抢跑。
2. **必须手动 `QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')`**，
   offscreen 平台字体族为 0，不加载则整屏无字。
3. 需要"已连接"状态的图：**先 `link.open()` 再建窗口**，反之 ConnectionBar 会错过 `opened` 信号。

---

## 5. 踩坑档案（改代码前必读）

### 5.1 theme 四个坑

| # | 坑 | 解 |
|---|---|---|
| ① | `setTheme()` 不管顶层 `QDialog` 背景 | `QPalette` + 窗口 QSS 双保险（已收敛进 `theme.apply_theme`） |
| ② | `ElevatedCardWidget` 底色不跟随主题 | 显式 `setBackgroundColor()`；**先重建卡片、再上色**，反了被覆盖 |
| ③ | 字体族落到 SimSun | `setFontFamilies` / 窗口 `setFont` 都无效 → 建好后逐个 `setFont`（`theme.fix_fonts`） |
| ④ | **qfluentwidgets 出厂强调色是青绿 `#009faa`** | 必须在 `apply_theme` 里 `setThemeColor(C_PRIMARY)`，否则所有 Primary 按钮都是绿调 |

### 5.2 QSS 与控件

| 坑 | 现象 | 解 |
|---|---|---|
| QSS `::item` 规则 + `item.setBackground()` | 背景**静默不画** | 用 delegate `paint` 直接画（见状态色条） |
| cellWidget + QSS `::item` padding | 10px 列被 padding 榨成 **0 宽** | 同上，别用 cellWidget 做窄装饰 |
| qfluentwidgets 自绘按钮 + `setStyleSheet` | **文字重影**（自绘一次 + QSS 再画一次） | 这类按钮改用**原生 `QPushButton`** + QSS；主按钮保留原生自绘不套 QSS |
| `QTextEdit` 光标残留 `charFormat` | 提示消息着色后，**串口数据继承该颜色** | 统一 `_insert()` 入口，每次都 `setCharFormat(空格式)` |
| `EditableComboBox.setCurrentText` | 只吃**列表内**的值，列表外**静默忽略** | 一律用 `setText()`（能设任意值且正常发信号） |
| 下拉框宽度 | 文字被裁（`BMU debug` 需 ≥127px、`115200` 需 ≥100px） | 按 `QFontMetrics` 实测，别拍脑袋 |
| `ConnectionBar` 初始状态 | 链路先打开后建窗 → 显示「未连接」但徽章绿 | `_sync_state()` 在 `__init__` 末尾按 `link.is_open` 对齐 |
| 冒烟里断言 `QTextEdit` 格式 | 按块序号定位**不可靠**（末尾空块 / 无换行追加都会偏） | **按内容定位 fragment**（`_fg_of(needle)`） |

### 5.3 按钮配色（已定稿）

| | 浅色 | 深色 |
|---|---|---|
| 工具条按钮 | 白底 + 蓝描边 `#6a9bf0` + 蓝字/图标 `#1d4ed8` | 暖米底 `#33301f` + 暖金字/图标 `#ffe0a3` |
| 主按钮 | 深蓝实心（原生） | 同 |
| 撤销型主按钮（断开） | 浅蓝 tint | 同 |

一屏**只留一个深蓝实心主按钮**；状态开关（锁定/定时中）用主色激活态；其余按钮安静。

---

## 6. 旧 UI 退役

**唯一判据：`Serial_thread.py` 能整文件删掉**（删不掉说明还有窗口抱着老实现）。

| 旧窗口 | 位置/入口 | 新实现 | 状态 |
|---|---|---|---|
| `BmuConsoleWindow` | `UIClass/`，主窗口 `show_bmu_console_window` | `apps/console_app.py` | 待退役 |
| `BatchFlashDownWindow` | `UIClass/`，主窗口 `show_BatchFlashDownWindow` | `apps/transfer_app.py` | 待退役 |
| 单发下载 | 主窗口 `show_FlashDownWindow` | 并进 transfer（单发 = 一个任务） | 待退役 |
| `SerialSendWindow` | `UIClass/`，主窗口 `Serial_Send_Window_Show` | `apps/sc422_app.py` | 待退役 |
| `CanWindow`（旧 CAN） | `JiangCan_Tools/`，主窗口 `Can_Window_Show` | 未开工 | — |
| `NewCanWindow`（新 CAN，1409 行） | `UIClass/`，主窗口 `Can_New_Window_Show` | 未开工（迁移主目标） | — |
| `FTPWindow` / `ReadWindow` / `TableViewWindow` | `UIClass/` | 未定 | 未定 |

主窗口（`FileFIle.py`）里的其它残留能力：`IrRePOWER`（复位遥控）、`IrVersionCheck`（版本查询）
——直接调 `Ycyk_Worker` 发帧，未收进任何页面。

遗留不修项：`Serial_thread` 的 `recv(13)` 死锁等问题**不修**，随文件一起退役。

---

## 7. 真机验收清单（未做，做之前新代码都算未验证）

### A. 控制台（debug 口 · 115200 8N1）

- [ ] 预设选 `BMU debug` → 打开 → 徽章变「已连接」绿
- [ ] 发 `version`，看回显；发 `help` 看命令表
- [ ] 勾 `hex 显示`，确认收到的是**原始字节**（不是替换字符）
- [ ] 拔线：应出现红色 `[!]` 错误行，徽章转「故障」

### B. 文件传输（422 口 · 921600 8O1）

- [ ] 预设选 `SC 422` → 打开（**校验位必须是 Odd**——这是 P0 修复点）
- [ ] 拖入小文件 → `开始` → 看**状态色条 灰→蓝→绿**、行内进度条同色
- [ ] 传输中：总进度条随队列状态变色（运行蓝 / 全完成绿 / 有失败红）
- [ ] 点「暂停」→ 按钮变「继续」→ 点回；点「停止」→ 弹二次确认
- [ ] 失败即中止开关：勾选后单点失败应整队列停止

### C. SC422 收发台

- [ ] 发心跳帧 `EB 90 01 80 C0 00 00 01 00 1D FE A0`，看是否回 `1A CF ... 00 1F ...`
      （按实际业务发对应的请求帧）
- [ ] 定时 100ms → 观察 `已发 N 次` 递增、RX 行成对出现
- [ ] 切 `ascii 视图`：`\r\n` 与高位字节应显示为 `.`
- [ ] 输入 `EB GG` → 下方红字应指出「含非法字符 G」

### D. 通用

- [ ] 三页各切一次浅/深主题：按钮/表格/日志/图标全部跟随
- [ ] 关窗重开：端口与参数（波特率/校验/预设）应被记住
- [ ] 关窗后任务管理器无残留 python 进程（读写线程已退）
- [ ] 同时开 console + transfer（不同口）：互不干扰

---

## 8. 待办

1. **真机验收**（见 §7）——未做之前，所有验证都只是"假设备自洽"
2. **CAN 页面迁移**：`NewCanWindow.py` 1409 行 → gui-ng；含 A 原型已有功能补齐（右键菜单等）
3. **主窗口迁移**：`FileFIle.py` / `new_mainwindows.py` → gui-ng 主窗口（四页接入、统一菜单/主题/连接管理）
4. **旧窗口退役**（§6，判据达成后）
5. **合并回主线**：`feat/gui-ng` → ? （未定：`feat/bmu-testkit` 或 `main`）
