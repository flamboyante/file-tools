# 归档说明 · ui_compare_20260918

> 本目录原为主工作区工程的 `exp/ui_compare/`，2026-09-18 产出，
> 长期处于未跟踪状态（不属于任何分支）；2026-10-09 **原样归档**进本仓库。

## 这是什么

2026-09-18 的「UI 方案 A/B 实测对比」实验现场 —— qfluentwidgets（A）vs QWebEngine（B）：

| 文件 | 内容 |
|---|---|
| `README.md` | 完整实验报告（对比数据、qfluentwidgets 版本调研、结论） |
| `out_*.png` | 渲染对比截图（浅/深 × fluent / webengine / mockup / B 原型） |
| `bench_*.py` | 性能基准脚本（A/B 吞吐测量） |
| `probe_*.py` / `probe_*.json` / `flag_matrix.json` | QWebEngine 特性与启动参数探针 |
| `render_*.py` / `card_page*.html` | 渲染对比脚本（把 mockup 卡片渲染出图） |
| `b_can_window.py` / `.html` | B 方案（QWebEngine）CAN 窗口原型 |
| `variant_result.json` | 变体裁剪结果 |

## 结论现状（已全部落地，此处仅存原始记录）

- 选型：**采用 A（qfluentwidgets）**；B 技术可行但维护成本高（QWebEngine 内置 Chromium 83 冻结等）
- 最终实现见 `apps/` 四页（console / transfer / sc422 / can）与 `docs/gui_ng/README.md`
- 后续更完整的一轮对比材料在 `docs/ui_three_way/`
