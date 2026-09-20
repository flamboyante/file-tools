# -*- coding: utf-8 -*-
"""B 方案 · QWebEngine 还原 v3 mockup。

════════════════════════════════════════════════════════════════
两条铁律（2026-09-18 实测，写错了不报错、只是静默失效）
════════════════════════════════════════════════════════════════
① QWebChannel 里 **JS → Python 的方法调用拿不到返回值**。
   ⇒ 所有「JS 要数据」的场景都必须「JS 发请求 → Python runJavaScript 回推」。
   本文件 = `bridge.ready()` → `push_init()`。

② Python 调 `runJavaScript` **必须在事件循环内部**。
   ⇒ 所有 JS 调用都经 `_js()` → `QTimer.singleShot(0, ...)`。

════════════════════════════════════════════════════════════════
另外两个坑
════════════════════════════════════════════════════════════════
③ Qt 5.15 的 QWebEngine 是 **Chromium 83**（2020-07）。
   `color-mix()` / `:has()` 不支持 —— b_page.html 里已改成预置色值。
④ 无交互式桌面时渲染进程会 FATAL（tsf_text_store.cc）；
   桌面环境不需要这个 flag，做成「仅在未显式设置时才注入」。

数据与收发仍然来自 uicmp.core —— 与 A 方案同源。
"""
import json
import os
import sys
import time

os.environ.setdefault(
    'QTWEBENGINE_CHROMIUM_FLAGS',
    '--disable-features=TSFImeSupport --disable-gpu --no-sandbox')

from PyQt5.QtCore import QObject, QUrl, QTimer, pyqtSlot          # noqa: E402
from PyQt5.QtWidgets import QDialog, QVBoxLayout                   # noqa: E402
from PyQt5.QtWebEngineWidgets import QWebEngineView                # noqa: E402
from PyQt5.QtWebChannel import QWebChannel                         # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from uicmp import core                                             # noqa: E402

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'b_page.html')


class _Bridge(QObject):
    """QWebChannel 桥（页面里叫 bridge）。

    铁律①：槽函数**一律无返回值**，只接收意图；
    数据由 Python 用 runJavaScript 推回去。
    """

    def __init__(self, win):
        super(_Bridge, self).__init__(win)
        self.win = win

    # ---- 初始化 ----
    @pyqtSlot()
    def ready(self):
        self.win.push_init()

    # ---- 总线 ----
    @pyqtSlot(str)
    def toggleBus(self, ch):
        self.win.do_toggle_bus(ch)

    # ---- 指令 ----
    @pyqtSlot(str, int)
    def toggleCmd(self, ch, idx):
        self.win.do_set_enabled(ch, idx, None)

    @pyqtSlot(str, int, bool)
    def setCmdEnabled(self, ch, idx, on):
        self.win.do_set_enabled(ch, idx, bool(on))

    @pyqtSlot(str, int)
    def sendOnce(self, ch, idx):
        self.win.do_send(ch, idx)

    @pyqtSlot(str)
    def addCmd(self, ch):
        self.win.do_add(ch)

    @pyqtSlot(str, int)
    def delCmd(self, ch, idx):
        self.win.do_del(ch, idx)

    @pyqtSlot(str, int)
    def copyCmd(self, ch, idx):
        self.win.do_copy(ch, idx)

    @pyqtSlot(str, int, int)
    def moveCmd(self, ch, idx, direction):
        self.win.do_move(ch, idx, direction)

    # ---- 全局 ----
    @pyqtSlot(bool)
    def setRun(self, on):
        self.win.running = bool(on)

    @pyqtSlot(bool)
    def setPause(self, on):
        self.win.paused = bool(on)

    @pyqtSlot()
    def toggleTheme(self):
        self.win.do_toggle_theme()


class BWindow(QDialog):
    """B 方案主窗口：一个 QWebEngineView 装下整个 v3 界面。"""

    def __init__(self, parent=None, mode=core.Mode.AUTO):
        super(BWindow, self).__init__(parent)
        self.setWindowTitle('B 方案 · QWebEngine 还原 v3')
        self.resize(1280, 900)

        self._dark = False
        self.running = False
        self.paused = False
        self.cmds = {core.CHAN_A: [], core.CHAN_B: []}
        self.buscount = {core.CHAN_A: [0, 0, 0], core.CHAN_B: [0, 0, 0]}
        self.stats = {'txA': 0, 'txB': 0, 'rx': 0, 'busy': 0, 'err': 0}
        self.busnote = {core.CHAN_A: '未连接', core.CHAN_B: '未连接'}
        self._pending = []          # 页面未就绪时缓存的监视行

        self._bus = core.CanBus(mode, self)
        self._bus.txResult.connect(self._on_tx)
        self._bus.rxFrame.connect(self._on_rx)
        self._bus.busState.connect(self._on_bus)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        v.addWidget(self.view)

        self.channel = QWebChannel(self.view.page())
        self.bridge = _Bridge(self)
        self.channel.registerObject('bridge', self.bridge)
        self.view.page().setWebChannel(self.channel)

        self._load_case()
        self.view.loadFinished.connect(lambda ok: None)
        self.view.load(QUrl.fromLocalFile(PAGE))

    # ------------------------------------------------- JS 调用唯一出口
    def _js(self, code):
        """铁律②：所有 runJavaScript 都排进事件循环，绝不直接调。"""
        QTimer.singleShot(0, lambda: self.view.page().runJavaScript(code))

    def _js_json(self, fn, obj):
        """把 obj 序列化成 JSON 传给 JS 函数。"""
        self._js('%s(%s);' % (fn, json.dumps(json.dumps(obj, ensure_ascii=False))))

    # ------------------------------------------------------------ 数据
    def _load_case(self):
        a, b = core.load_case()
        self.cmds[core.CHAN_A] = a
        self.cmds[core.CHAN_B] = b

    def _sub_of(self, c, ch):
        """副标题：像 v3 那样写一个语义标签（快遥/慢遥/姿态…）。"""
        src = core.case_source()
        return c.name

    def _cmd_json(self, c, ch, idx):
        frames = []
        for f in c.frames:
            frames.append({'id': f.id,
                           'data': ' '.join('%02X' % b for b in f.data)})
        cnt = '\u221e' if c.count <= 0 else str(c.count)
        state, kind = '', 'gray'
        if getattr(c, '_last_ok', None) is True:
            state, kind = '最近成功', 'green'
        elif getattr(c, '_last_ok', None) is False:
            state, kind = 'TX 失败 · 总线错误', 'red'
        return {
            'name': c.name,
            'sub': '双击展开 · 右键更多',
            'interval_ms': c.interval_ms,
            'count': cnt,
            'enabled': bool(c.enabled),
            'state': state,
            'stateKind': kind,
            'frames': frames,
        }

    def _cmds_json(self):
        return {core.CHAN_A: [self._cmd_json(c, core.CHAN_A, i)
                              for i, c in enumerate(self.cmds[core.CHAN_A])],
                core.CHAN_B: [self._cmd_json(c, core.CHAN_B, i)
                              for i, c in enumerate(self.cmds[core.CHAN_B])]}

    def _bus_json(self):
        out = {}
        for ch in core.CHANNELS:
            tx, rx, err = self.buscount[ch]
            out[ch] = {'open': self._bus.is_open(ch), 'baud': core.BAUD_LABEL,
                       'tx': tx, 'rx': rx, 'err': err, 'note': self.busnote[ch]}
        return out

    # ----------------------------------------------------- 推送（Python→JS）
    def push_init(self):
        self._js_json('onInit', {
            'note': '用例：%d + %d 条' % (len(self.cmds[core.CHAN_A]),
                                          len(self.cmds[core.CHAN_B])),
            'bus': self._bus_json(),
            'cmds': self._cmds_json(),
            'stats': self.stats,
        })
        for m in self._pending:
            self._js_json('onLine', m)
        self._pending = []

    def push_cmds(self):
        self._js_json('onCmds', {'cmds': self._cmds_json(), 'stats': self.stats})

    def push_bus(self, ch):
        self._js('onBus(%s, %s, %s);' % (
            json.dumps(ch), 'true' if self._bus.is_open(ch) else 'false',
            json.dumps(self.busnote.get(ch, ''), ensure_ascii=False)))

    def push_bus_count(self, ch):
        tx, rx, err = self.buscount[ch]
        self._js('onBusCount(%s,%d,%d,%d);' % (json.dumps(ch), tx, rx, err))

    def push_stats(self):
        self._js_json('onStat', self.stats)

    def add_line(self, ch, direction, fno='', fid='', data=''):
        m = {'time': time.strftime('%H:%M:%S.') + ('%03d' % (int(time.time() * 1000) % 1000)),
             'ch': ch, 'dir': direction, 'fno': fno, 'id': fid, 'data': data}
        self._js_json('onLine', m)

    # ----------------------------------------------------- JS 回调 → 业务
    def do_toggle_bus(self, ch):
        if self._bus.is_open(ch):
            self._bus.close_channel(ch)
        else:
            self._bus.open_channel(ch)

    def do_set_enabled(self, ch, idx, value):
        lst = self.cmds.get(ch) or []
        if 0 <= idx < len(lst):
            c = lst[idx]
            c.enabled = (not c.enabled) if value is None else bool(value)
            self.push_cmds()

    def do_send(self, ch, idx):
        lst = self.cmds.get(ch) or []
        if not (0 <= idx < len(lst)):
            return
        self._bus.send_once(lst[idx])

    def do_add(self, ch):
        from WorkClass.CANCommandScheduler import CanCommand, CanFrame
        cmd = CanCommand('新指令 %d' % (len(self.cmds[ch]) + 1), ch, 500, -1, False,
                         [CanFrame(0x31801, [0x00, 0x5A, 0x5A])])
        self.cmds[ch].append(cmd)
        self.push_cmds()

    def do_del(self, ch, idx):
        lst = self.cmds.get(ch) or []
        if 0 <= idx < len(lst):
            lst.pop(idx)
            self.push_cmds()

    def do_copy(self, ch, idx):
        lst = self.cmds.get(ch) or []
        if 0 <= idx < len(lst):
            c = lst[idx].copy()
            c.name = c.name + ' 副本'
            lst.insert(idx + 1, c)
            self.push_cmds()

    def do_move(self, ch, idx, direction):
        lst = self.cmds.get(ch) or []
        j = idx + direction
        if 0 <= idx < len(lst) and 0 <= j < len(lst):
            lst[idx], lst[j] = lst[j], lst[idx]
            self.push_cmds()

    def do_toggle_theme(self):
        self._dark = not self._dark
        self._js('setDark(%s);' % ('true' if self._dark else 'false'))

    # ------------------------------------------------- 业务 → 推送
    def _on_bus(self, ch, opened, msg):
        self.busnote[ch] = msg
        self.push_bus(ch)
        self.add_line('SYSTEM', 'SYS', '', '', '通道 %s：%s' % (ch, msg))

    def _on_tx(self, ch, ok, tag, idx, total):
        tx, rx, err = self.buscount[ch]
        self.buscount[ch] = [tx + (1 if ok else 0), rx, err + (0 if ok else 1)]
        if ok:
            if ch == core.CHAN_A:
                self.stats['txA'] += 1
            else:
                self.stats['txB'] += 1
        else:
            self.stats['err'] += 1
        # 标记卡片与帧，并取出该帧的 ID / data 用于监视行
        fid, fdata = '', ''
        for i, c in enumerate(self.cmds.get(ch) or []):
            if c.name == tag:
                c._last_ok = bool(ok)
                if idx < len(c.frames):
                    fid = '0x%X' % c.frames[idx].id
                    fdata = ' '.join('%02X' % b for b in c.frames[idx].data)
                self._js('onTxMark(%s,%d,%s);' % (json.dumps(ch), i,
                                                  'true' if ok else 'false'))
                self._js('onFrameMark(%s,%d,%d,%s);' % (json.dumps(ch), i, idx,
                                                        'true' if ok else 'false'))
                break
        self.push_bus_count(ch)
        self.push_stats()
        self.add_line(ch, 'TX' if ok else 'ERR', '帧%d/%d' % (idx + 1, total),
                      fid, fdata if ok else ('发送失败 · 底层返回码非 1'))

    def _on_rx(self, ch, fid, data):
        tx, rx, err = self.buscount[ch]
        self.buscount[ch] = [tx, rx + 1, err]
        self.stats['rx'] += 1
        hexs = ' '.join('%02X' % b for b in data)
        self.push_bus_count(ch)
        self.push_stats()
        self.add_line(ch, 'RX', '应答', '0x%X' % fid, hexs)

    def closeEvent(self, e):
        try:
            self._bus.shutdown()
        except Exception:
            pass
        super(BWindow, self).closeEvent(e)


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = BWindow()
    w.show()
    sys.exit(app.exec_())
