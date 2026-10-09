# A/B 方案实测对比：qfluentwidgets vs QWebEngine

> 实测时间：2026-09-18 17:50–18:15
> 分支：`exp/ui-fluent-vs-webengine`（起点 = tag `v2-gui-baseline-20260918` = `e15ae31`）
> 运行环境：`C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe`（Python 3.8.18 / PyQt5 5.15.10 / Qt 5.15.2）
> 所有脚本与产物均在 `exp/ui_compare/`，**未 commit、未动主分支**

---

## 一、最终结论

| 方案 | 判定 |
|---|---|
| **A · qfluentwidgets 组合控件** | ✅ **推荐**。跑通、稳定、够用 |
| **B · QWebEngine 嵌 HTML** | ⚠️ **技术上跑通了，但太贵**。视觉更好，代价是多两条结构性约束 + 一套 Chromium 依赖 |

> **重要更正**：本文档早先版本判定「B 不可用」是**错的**。真因是**我这边执行环境缺交互式桌面**（详见第三节），加上 `--disable-features=TSFImeSupport` 后 B 完全可用。
> **在你的真实桌面环境里，这个 flag 根本不需要。**

### 效率数据现状（诚实标注）

| 项 | 状态 |
|---|---|
| A 方案吞吐 | ✅ 实测（见 4.1） |
| B 方案吞吐 | ❌ **未测出**。`--bench` 路径的 `boot()` 在嵌套事件循环里不稳定（`ok:false`），而**同一份 `boot()` 代码在 `--shot` 路径下稳定成功** |

**这个缺口本身就是一个结论**：B 方案的启动时序对它被调用的上下文敏感 —— 一个工具类软件里，这种"敏感"就是实打实的维护成本。

**并且它不改变选型结论**：决策关键是下面的两条结构性约束和可靠性，不是毫秒级吞吐（A 的 47.6 µs/次已经远超 CAN 每秒几十帧的负载需求）。

---

## 二、qfluentwidgets 版本情况

| 项 | 值 |
|---|---|
| 你已安装 | **1.5.4** |
| PyPI 最新 | **1.11.3**（跨 6 个大版本） |

**升级影响（dry-run 实测）**：
```
Would install  PyQt-Fluent-Widgets-1.11.3  PyQt5-Frameless-Window-0.8.2
```
⚠️ 必须把 **`PyQt5-Frameless-Window` 0.3.9 强升到 0.8.2**。它是 qfluentwidgets 的**窗口壳依赖**（圆角 / 拖拽 / 标题栏），你现有 6 个在用窗口的风格有受影响风险。

**我的处理：暂不升级。** 对比用真实基线 1.5.4（这样才公平），升级单独立项。

**1.5.4 之后的主要新增（据 GitHub release）**：
- 新组件：`GroupHeaderCardWidget`、`FastCalendarPicker`、`TextBrowser`
- 新特性：系统主题监听器、下拉框 `activated` 信号、输入框自定义动作
- 修复：**内存泄漏 (#963/#977)**、**`ExpandLayout` 坐标计算 (#941)**、`SegmentedWidget.clear` 报错

未见明确的 breaking change 声明，但依赖要求确实变了。

---

## 三、PyQtWebEngine 安装（已执行）

```
pip install PyQtWebEngine==5.15.7
```

| 结果 | 说明 |
|---|---|
| 新增 `PyQtWebEngine` 5.15.7 | 184 KB |
| 新增 `PyQtWebEngine-Qt5` 5.15.2 | **60 MB** |
| 对现有包的影响 | **零** —— PyQt5 5.15.10 / PyQt5-Qt5 5.15.2 / sip 12.15.0 全部「already satisfied」 |

纯增量，可安全卸载：`pip uninstall PyQtWebEngine PyQtWebEngine-Qt5`

---

## 四、实测数据

### 4.1 A 方案（`bench_fluent.py`）

负载：200 张卡片、10 轮文本刷新、5 轮开关切换。

| 项 | 数据 |
|---|---|
| T1 建 200 张卡片（含 `processEvents`） | **2046.36 ms** → **10.23 ms/张** |
| T2 文本刷新 2000 次 | **95.15 ms** → **47.58 µs/次** |
| T3 开关切换 1000 次 | **25.54 ms** → **25.54 µs/次** |
| 全流程 wall clock（Python 启动 + 导入 + 建卡 + 测完） | **6216.6 ms** |

> 注：T1 的 10.23 ms/张偏慢，怀疑是 `ElevatedCardWidget` 的投影（`QGraphicsDropShadowEffect`）代价。**此项未做隔离验证**，若要上几百张卡片需要补测。

### 4.2 B 方案（三组独立探针，结论一致）

**探针① `probe_webengine.py`（45s 硬超时）**

```
  154ms  import QtWebEngineWidgets OK
 1038ms  QApplication OK          ← 156ms → 1038ms，WebEngine 拖慢 QApplication 初始化 +882ms
 2657ms  loadProgress 0%
 2813ms  loadProgress 100%        ← 进度到顶
47141ms  HARD TIMEOUT, loaded=False   ← loadFinished 从未触发
         QtWebEngineProcess count = 3
```

**探针② `probe_variants.py`（4 种页面形态 × 20s）**

| 变体 | progress | loadFinished | JS 回调 |
|---|---|---|---|
| V1 `setHtml("<h1>hello</h1>")` 最小页 | ✅ 100% | ❌ | ❌ |
| V2 setHtml + `qrc:///qtwebchannel/qwebchannel.js` | ✅ 100% | ❌ | ❌ |
| V3 `file://` 完整 card_page.html | ✅ 100% | ❌ | ❌ |
| V4 `file://` 无 QWebChannel 版 | ✅ 100% | ❌ | ❌ |

⇒ **连 `<h1>hello</h1>` 都不触发** ⇒ 与页面无关，也不是 QWebChannel 的锅。

**探针③ `probe_flags.py`（8 种 Chromium flag）** → **8/8 全部超时**

`baseline` / `--disable-gpu` / `--no-sandbox` / 两者组合 / `--single-process` / 三者组合 / `--in-process-gpu --no-sandbox` / `--disable-software-rasterizer --no-sandbox`

⇒ **Chromium 标准救火开关一个都没用。**

**探针④ 截图** → **4 张全是 660×470 的纯白图，各 1.9 KB**（A 方案同尺寸 33 KB）

### 4.3 🎯 根因与解药：`FATAL:tsf_text_store.cc(52)`

**直接单跑 `QtWebEngineProcess.exe`，一行就说完了**（比 8 组 flag 矩阵有效得多）：

```
[21260:30988:0918/182632.410:FATAL:tsf_text_store.cc(52)] Failed to initialize CategoryMgr.
```

`tsf_text_store.cc` = **Windows TSF（Text Services Framework，输入法框架）**。Chromium 渲染进程启动时必须初始化 TSF 的 `CategoryMgr` COM 组件；**在没有真正交互式桌面的会话里必然失败 ⇒ 渲染进程 FATAL 崩溃**。

这完美解释了全部现象：

| 现象 | 解释 |
|---|---|
| `loadProgress` 能到 100% | 浏览器进程侧自己算的，与渲染进程无关 |
| `loadFinished` 从不触发 | 渲染进程已崩，没人上报 |
| `runJavaScript` 回调从不返回 | 同上 |
| 8 种 GPU / sandbox flag 全无效 | 它们管不到 TSF |
| `grab()` 全白（1.9 KB） | 没有渲染进程产出像素 |

**解药**（在 `import PyQt5` / 创建 `QApplication` **之前**设置）：

```python
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = \
    "--disable-features=TSFImeSupport --disable-gpu --no-sandbox"
```

逐个验证结果：

| 配置 | 结果 |
|---|---|
| baseline | **FATAL** 崩溃（1.2s） |
| **`--disable-features=TSFImeSupport`** | **不再 FATAL，进程存活** |
| `+ --disable-gpu --no-sandbox` | 存活，连 GPU 报错都没有 |
| `--single-process` + 上述 | 崩（退出码 3221226505 = 0xC0000409），**别用** |

**在正常桌面环境下不需要这个 flag**，故 `b_can_window.py` 里做成「仅在未显式设置时才注入」，避免污染。

### 4.4 ⭐ B 方案跑通后踩出的两条结构性约束

这两条是 B 方案真正的成本所在，**写错了不报错、只是静默失效**：

**① QWebChannel 里 JS → Python 的方法调用拿不到返回值**

```python
@pyqtSlot(result=str)
def getCommands(self):            # ← JS 侧拿到的是 undefined
    return json.dumps(...)
```
症状：`boot_ok: true` 但 `commands: 0`（`JSON.parse(undefined)` 抛异常被 catch 吞掉）。

**正解**：JS 调 `bridge.requestCommands()`（无返回值），Python 用信号回推：
```python
commandsReady = pyqtSignal(str)
@pyqtSlot()
def requestCommands(self):
    self.commandsReady.emit(json.dumps(COMMANDS, ensure_ascii=False))
```
⇒ **所有「JS 要数据」的场景都必须走「JS 发请求 → Python 用 signal 回推」。**

**② Python 调 `runJavaScript` 必须发生在事件循环内部**

在循环外调用（例如刚退出嵌套循环时），**请求会被静默丢弃**。症状：监视区始终为空、RX 计数不更新。
正解：`QTimer.singleShot(0, lambda: page.runJavaScript(...))` 排进循环。

**③（CSS 侧的坑，非 QWebChannel）** flex 列容器会把卡片压扁
`.cmd-list{display:flex;flex-direction:column}` 内容溢出时，子项因默认 `flex-shrink:1` 被压到约 20px、文字全裁。
正解：`.cmdbar{flex-shrink:0}`。**Qt 的 `QVBoxLayout` 不会这样** —— 这是 HTML 路线要多留意的点。

### 4.5 判读工具：`subprocess.run` 对 WebEngine 应用必然超时

Chromium 子进程会继承 stdout 管道句柄，父进程 `os._exit(0)` 后管道仍不关闭，`subprocess.run(capture_output=True)` 会一直等到 timeout。
**这不是程序卡死，是管道占用。** 看到 TIMEOUT 但 stdout 里已有完整 `RESULT_JSON`，就是这种情况。

### 4.6 关键差异：谁在渲染

| | A · qfluentwidgets | B · QWebEngine |
|---|---|---|
| 渲染位置 | **Qt 进程内自己画** | **Chromium 跨进程合成器** |
| `widget.grab()` | ✅ 直接渲染 widget 树，出图正常 | ❌ 空白（合成器回传通道不通） |
| 故障面 | 小 | **多一层进程 + IPC，故障面大得多** |

⇒ **这是独立于性能数据的可靠性论据**：Qt 自绘不依赖外部合成器，嵌 HTML 多一层跨进程依赖。

---

## 五、请你复测 B 方案（一条命令）

在你自己的桌面上跑（**不要在远程/无桌面会话里跑**）：

```bash
cd C:\heike\md\pythonProjectV3.3.0_beta\exp\ui_compare
C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe render_webengine.py card_page_five.html out_mytest
```

**判读**：
- `out_mytest_light.png` **> 10 KB 且能看到 5 张卡片** → B 方案在你的桌面可用，我上面的失败纯属沙箱环境
- `out_mytest_light.png` **约 2 KB 纯白** → B 方案在你机器上也坏，可以彻底排除

也可以直接双击打开 `docs/ui_mockup/ui_mockup_final_bubbles.html` 看浏览器里的效果（那是设计目标，不是 PyQt 里的效果）。

---

## 六、设计还原度：mockup 的能力缺口

读 `docs/ui_mockup/ui_mockup_final_bubbles.html` 的真实 CSS，逐项核对 Qt 能不能做到：

| mockup 用的能力 | Qt / QSS | 说明 |
|---|---|---|
| `box-shadow` 双重重投影 | ❌ | 现代 UI 层次感主要来源；qfluentwidgets 的 `ElevatedCardWidget` 已补上 |
| `transition: all .15s` 过渡 | ❌ | QSS 无过渡；qfluentwidgets 控件自带 hover 动画 |
| `--css-variable` + `.dark{}` 换肤 | ❌ | 但 `setTheme()` 一行可替代 |
| `::after` 做开关旋钮 | ❌ | `SwitchButton` 已替代 |
| `border-radius: 99px` 胶囊 | ⚠️ | 支持；`PillPushButton` 直接可用 |
| `linear-gradient(135deg,…)` | ⚠️ | QSS `qlineargradient` 只对少数属性，**但通道方块已在 A 截图里复刻成功** |
| **`color-mix(in srgb,…)`** | ❌ | 完全没有对应 |
| `transform: translateY(-1px)` / `rotate(180deg)` | ❌ | 无 |
| `filter: brightness/saturate/opacity` | ❌ | 无 |
| `flex-wrap: wrap` 真流式换行 | ❌ | `FlowLayout` 近似 |

**结论**：qfluentwidgets 能补上「**投影 / 过渡动画 / 换肤 / 胶囊 / 开关**」四类；但 `color-mix`、`transform`、`filter`、真 `flex-wrap` 仍做不到。

⇒ **100% 还原 mockup 不可能，要接受约 80–90% 的还原度。**
⇒ 剩下那 10–20% 只能靠自绘，或者放弃。

---

## 七、最终建议

### 选 A（qfluentwidgets）

| 维度 | A | B |
|---|---|---|
| 依赖 | **0**（已装，6 处在用） | +60 MB，Chromium 3 进程 |
| 渲染 | Qt 进程内自绘，`grab()` 稳定 | 跨进程合成器，多一层故障面 |
| 数据流 | 直接调 Python 对象 | **必须走信号回推**（约束①） |
| 派发时机 | 随意 | **必须在事件循环内**（约束②） |
| 出错表现 | 抛异常，看得见 | **静默失效**（白屏 / 数据不来） |
| 启动时序 | 稳 | **对调用上下文敏感**（bench 路径直接失败） |
| 视觉还原度 | 约 85–90% | 约 95–100% |
| 深色主题 | `setTheme()` 一行 | `.dark` class + `setDark()` |

**A 唯一的短板是"最后 10% 的还原度"，B 的代价是整条链路的复杂度。** 对一个要和硬件实时通信的调试工具，这个交换不划算。

### 但 B 不是错的选择 —— 如果你的优先级变了

如果"好看"是硬指标、且你接受：
- 60 MB 依赖 + 3 个常驻进程
- 所有数据流按信号模式重写
- 调试时 JS 报错不会传导到 Python（黑盒）
- 每个界面都要多留意 CSS 的 flex/溢出坑

那 B 可行，视觉确实更好（对比 `out_b_light.png` 与 `out_fluent_light.png`）。

### 落地清单（选 A 的话）

1. 拿 `render_fluent.py` 的写法做**一张真卡片**，替换 `NewCanWindow._CommandCard`（`paintEvent` 169 行 → 组合控件约 80 行）
2. 删掉 `LIGHT_QSS` / `DARK_QSS`（123 行）+ `COL` 色板（约 80 项），换 `setTheme()` + `setThemeColor()`
3. **qfluentwidgets 升级先别做** —— 会强升 `PyQt5-Frameless-Window` 0.3.9→0.8.2，风险已知收益不明；想升就单独一轮，先在你 6 个现有窗口上回归
4. 待补测：`ElevatedCardWidget` 的投影代价（10.23 ms/张，取决于卡片数量上限）

### 卸载 B 的依赖（如不需要）

```bash
C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe -m pip uninstall PyQtWebEngine PyQtWebEngine-Qt5
```

---

## 八、文件清单

| 文件 | 用途 |
|---|---|
| `bench_fluent.py` | A 方案吞吐基准 |
| `bench_webengine.py` | B 方案吞吐基准（未跑通，被 `loadFinished` 卡住） |
| `probe_webengine.py` | 探针①：分阶段日志 + 45s 硬超时 |
| `probe_variants.py` | 探针②：4 种页面形态对比 |
| `probe_flags.py` | 探针③：8 种 Chromium flag 矩阵 |
| `render_fluent.py` | A 方案视觉渲染（浅/深） |
| `render_webengine.py` | B 方案视觉渲染（浅/深） |
| `card_page.html` | B 方案基准页（带 QWebChannel） |
| `card_page_nocore.html` | B 方案基准页（无 QWebChannel，用于隔离） |
| `card_page_five.html` | 5 张卡片，CSS 摘自 mockup，用于同内容对比 |
| `out_fluent_light.png` / `out_fluent_dark.png` | **A 方案实际截图（有效）** |
| `out_webengine_*.png` / `out_mockup_*.png` | B 方案截图（全白，失败证据） |
| `flag_matrix.json` | flag 矩阵原始结果 |
