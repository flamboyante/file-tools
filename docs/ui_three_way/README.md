# A / B 方案对比 · 还原 `ui_mockup_v3.html`

> 更新：2026-09-20　分支 `exp/ui-three-way`　工作树 `C:\heike\uicmp`
> 运行环境：`C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe`（Python 3.8.18）
> 对比图：`compare_ab.png`（上排浅色 / 下排深色）

（C 方案 —— 原生 QSS + QPainter 全自绘 —— 已按要求删除，不在本次范围内。）

---

## 一、怎么保证对比公平

**两方案共用 `uicmp/core.py`** —— 数据、设备、收发全部同源，**差异只允许在渲染层**。
数据统一读 `uicmp/case.json`（3 条真实星上指令：单帧 / 5 帧 / B 通道各一条）。

```
WorkClass/CANCommandScheduler   零 Qt，数据 + 调度
WorkClass/CanStreamWorkers      QThread，收发
uicmp/core.py       ← 共享层   无渲染代码（257 行）
uicmp/impl_a_fluent.py          A：qfluentwidgets 组合控件（909 行）
uicmp/impl_b_web.py + b_page.html   B：QWebEngine + HTML/CSS/JS（344 + 约 600 行）
uicmp/launcher.py               统一入口，两个独立窗口可并排
```

---

## 二、还原度

以 `docs/ui_mockup/ui_mockup_v3.html` 为基准，逐项核对：

| v3 的元素 | A | B |
|---|---|---|
| 顶部总线卡片 ×2（大徽章 + 波特率 + TX/RX/错误 + 开关） | ✅ | ✅ |
| A/B Tab 切换 | ✅ | ✅ |
| 编辑工具条（添加 / 复制 / 删除 / ↑↓） | ✅ | ✅ |
| 指令卡胶囊排（帧数 / 周期 / 次数 / 状态） | ✅ | ✅ |
| 行内 badge（运行中 / 停止） | ✅ | ✅ |
| 双击展开帧明细 | ✅ | ✅ |
| 监视区每帧一个气泡卡（左色条 + 通道/方向徽章 + 帧号 + ID + data） | ✅ | ✅ |
| 监视过滤（通道 A/B、TX/RX/ERR）+ 暂停 / 清空 | ✅ | ✅ |
| 底部统计卡 ×5 + 图例 | ✅ | ✅ |
| 右键菜单 | ❌（Qt 侧未接） | ✅ |
| 运行锁 + 开始发送 | 按钮在，未真定时 | 按钮在，未真定时 |
| 导入/导出 JSON·Excel | ❌ 提示未接入 | ❌ 提示未接入 |
| 编辑帧 / 修改间隔 | ❌ 提示未接入 | ❌ 提示未接入 |

**结论：主界面还原度 A ≈ 90%，B ≈ 95%。** 差距集中在右键菜单和三个"未接入"的编辑功能上——
这些需要后端支持，不只是画界面。

**B 更高的那 5%** 来自三处 A 做不到的 CSS 能力：
双层不同模糊半径的 `box-shadow`、`transform: translateY()` hover 位移、`transition` 过渡动画。
静态截图里看不出来，**鼠标划过卡片时差别明显**——请你自己试。

---

## 三、B 的硬边界：Chromium 83

`QWebEngine`（Qt 5.15.2）内置 **Chromium 83（2020-07）**。实测支持情况：

| 能力 | 支持 | 备注 |
|---|---|---|
| 双层 `box-shadow` | ✅ | A 做不到，B 的视觉优势来源 |
| `translateY` / `transition` | ✅ | 同上 |
| `linear-gradient` / `backdrop-filter` | ✅ | |
| **`color-mix()`** | ❌ | Chromium 111+ 才有 |
| **`:has()`** | ❌ | Chromium 105+ 才有 |

**v3 mockup 自身在这个内核下的还原度 ≈ 99%** —— 它只在
`.cmdbar.running-on` 一处用了 `color-mix`。`b_page.html` 里已改成预置色值。

> ⚠️ **这是 B 方案的长期风险**：Qt 5.15 已停止功能更新，Chromium 版本号不会再涨。
> 想用新 CSS 特性只能升 Qt 6。**v3 恰好没踩到坑，不等于 Web 没有坑。**

---

## 四、踩坑记录（都是实测，会静默失效的那种）

### A 方案（qfluentwidgets 1.11.3）

1. **`setTheme()` 不管顶层 `QDialog` 的背景** —— 只换文字色，背景仍浅 ⇒ 白字白底。要用 `QPalette` 补。
2. **`ElevatedCardWidget` 的底色不跟随 `setTheme()`** —— 浅色建卡 `#fafafa`，切深色后**仍是 `#fafafa`**。
   要用 `setBackgroundColor()` 显式指定。
   ⚠️ **顺序很重要：先重建卡片、再上色**。反过来会被重建覆盖（我在这里踩了两次）。
3. **`QLabel` 的 QSS `background` 默认不绘制** —— 胶囊/徽章要 `setAttribute(Qt.WA_StyledBackground, True)`。
4. **`SwitchButton` 默认带 "On"/"Off" 文本**（1.11.x 新增），要 `setOnText('')` 关掉。
5. **字体族会落到 SimSun（宋体）** —— qfluentwidgets 的 label 在构造时 `QFont()`
   **只设了 `pixelSize`，没设 family**，family 取的是 `QApplication.font()`
   （中文 Windows 上是 SimSun）。
   - `q.setFontFamilies(['Segoe UI', 'Microsoft YaHei'])` —— **实测无效**（仍是 SimSun）
   - `self.setFont(...)`（窗口级）—— **也无效**（label 是显式 setFont 的，不走继承）
   - ✅ 唯一可行：控件建好之后**逐个 `setFont` 把 family 拨正**（见 `_fix_fonts()`）
   - 字号也不完全一致：qfluentwidgets 是 14/12，v3 是 13.5/10.5，已用 QSS 显式对齐

### B 方案（QWebEngine）

1. **JS → Python 拿不到返回值** ⇒ 必须「JS 发请求 → Python 用 signal/runJavaScript 回推」。
2. **`runJavaScript` 必须在事件循环内**，循环外调用被**静默丢弃**。
3. **`QtWebEngineWidgets` 必须在 `QApplication` 之前导入**，否则硬报 ImportError。
4. **无交互式桌面下渲染进程 FATAL**（`tsf_text_store.cc`）⇒ `--disable-features=TSFImeSupport`。
   你的真实桌面不需要这个 flag。
5. **CSS `flex-shrink` 会把卡片压扁**（`.card{flex-shrink:0}`）。Qt 的 `QVBoxLayout` 不会这样。
6. **`subprocess.run(capture_output=True)` 对 WebEngine 应用必然超时** —— 是管道被 Chromium 子进程占用，不是卡死。

---

## 五、怎么验证（你那边）

**打开两个方案**：主程序命令栏 → 「UI 方案对比」→ 两个按钮，可同时开两个窗口并排看。

```bash
cd C:\heike\uicmp
C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe FileFIle.py
```

**重点看这几处**（截图看不出来的）：
- 鼠标划过指令卡：B 有位移 + 阴影加深，A 只有边框变色
- 切换深浅色：A 靠 `setTheme` + `setPalette`，B 靠 `.dark` class
- 双击卡片展开帧明细；右键卡片（**只有 B 有右键菜单**）
- 拖窗口改变大小：A 的指令区高度是算出来的，B 是 CSS 自然流

### 真机收发：需要先接线

设备能打开（`ECAN.is_open = True`，两通道 config+start 都成功），但**发送会阻塞** ——
CAN 发送需要总线上有其它节点发 ACK。

```
USBCAN-II:  CAN1_H ──── CAN2_H
            CAN1_L ──── CAN2_L
```

接好后跑 `python tools\raw_can_test.py`（判读见脚本末尾输出）。

**没有硬件时**：两边都支持模拟模式（AUTO 模式下真机打不开会自动回退），
打开通道会显示「已连接 · 模拟」，并真实模拟「A 发 → B 收」。

---

## 六、文件清单

| 文件 | 说明 |
|---|---|
| `uicmp/core.py` | 共享层：数据 + 设备 + 收发（257 行，无渲染代码） |
| `uicmp/case.json` | 统一测试用例 |
| `uicmp/impl_a_fluent.py` | A 方案（909 行） |
| `uicmp/impl_b_web.py` | B 方案 Python 侧（344 行） |
| `uicmp/b_page.html` | B 方案页面（CSS 取自 v3，仅改 color-mix 一处） |
| `uicmp/launcher.py` | 统一入口 |
| `tools/shot.py` | 出图（A 用 offscreen + 手动载字体；B 必须真实平台） |
| `tools/make_compare.py` | 拼对比图 |
| `tools/live_test.py` / `raw_can_test.py` | 真机验证 |
| `tools/probe_css.py` / `check_mockup_in_webengine.py` | 探测内核能力 / 验证 v3 在 QWebEngine 下的还原度 |
