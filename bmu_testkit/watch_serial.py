# -*- coding: utf-8 -*-
"""串口流量监视窗口（独立程序）。

监听本机 UDP 端口，实时显示 agent 进程通过 `mirror` 层广播的串口收发。

单独运行：
    python -m bmu_testkit.watch_serial
    python -m bmu_testkit.watch_serial --port 39527 --truncate 30

设计取舍：
  - **不打开串口**：只监听 UDP，因此与任何持有串口的进程都不冲突。
  - **默认截断显示**：一帧上千字节时全长展开会刷屏且无信息量，
    帧头 30 字节已足以判断身份；完整内容在日志文件里。
  - **批量刷新**：高频数据先入队，按固定间隔合并到界面，避免逐条刷新卡死。
"""

import argparse
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QTextCursor
from PyQt5.QtNetwork import QHostAddress, QUdpSocket
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# 允许直接以脚本方式运行（python bmu_testkit/watch_serial.py）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bmu_testkit.mirror.sinks import parse_event  # noqa: E402

DEFAULT_UDP_PORT = 39527
DEFAULT_TRUNCATE = 30
DEFAULT_VIEW = "hex"

# 载荷渲染方式：
#   hex   —— 字节流（422 帧、二进制协议用）
#   ascii —— 文本（BL/App 的日志打印用；不可打印字符显示为 '.')
VIEWS = ("hex", "ascii")

# 行组装（仅 ascii 视图有意义）
#   串口是字节流，内核按缓冲区状况切块返回，因此一条日志常被拆成多行显示
#   （实测 BL 日志按 1ms 一块刷出，一句话跨 6 行）。
#   开启后按 '\n' 拼回整行；若长时间没有换行（半行卡住），由 ASSEMBLE_FLUSH
#   兜底强制吐出，避免内容一直不显示。
ASSEMBLE_FLUSH = 0.3

# 帧头（含长度字段）长度；与 protocol/ycyk422.HEAD_LEN 一致
HEAD_LEN = 8

# 配色（浅色主题）
COLOR_TX = QColor("#1565C0")       # 蓝：发往设备
COLOR_RX = QColor("#2E7D32")       # 绿：设备返回
COLOR_ERROR = QColor("#C62828")    # 红：异常结果码
COLOR_NOTE = QColor("#6A1B9A")     # 紫：语义标注
COLOR_MUTED = QColor("#757575")    # 灰：省略提示

# 结果码只在**数据域为 3 字节**的应答里出现（文件传输类应答，总长 13），
# 位于帧内下标 10。心跳等短应答的数据域只有 2 字节，下标 10 是校验和高位，
# 不能拿它判异常 —— 否则校验和恰为 0xFF 的正常应答会被误标红。
ERROR_RESULTS = {0xFF, 0x11}

# 携带结果码的应答：帧头 8 字节 + 3 字节数据域 + 2 字节校验和 = 13
RESULT_FRAME_LEN = 13
RESULT_BYTE_IDX = 10

MAX_LINES = 5000                   # 环形缓冲上限


class SerialMonitorWindow(QMainWindow):
    """UDP 串口流量监视器。"""

    def __init__(self, port: int = DEFAULT_UDP_PORT,
                 truncate: int = DEFAULT_TRUNCATE, view: str = DEFAULT_VIEW,
                 title: str = None, assemble: bool = None, parent=None):
        super(SerialMonitorWindow, self).__init__(parent)
        self.view = view if view in VIEWS else DEFAULT_VIEW
        self.setWindowTitle(title or "Serial Monitor — 串口流量监视")
        self.resize(1180, 620)

        self.truncate = truncate
        self.paused = False
        self.only_error = False
        self._pending = []             # 待刷新事件队列
        self._line_count = 0
        self._pkt_count = 0

        # 行组装：ascii 视图默认开（日志口常被切碎），hex 视图无意义故强制关
        if assemble is None:
            assemble = (self.view == "ascii")
        self.assemble = bool(assemble) and self.view == "ascii"
        self._asm_buf = bytearray()    # 行组装缓冲区（原始字节）
        self._asm_meta = None          # 该行首段事件的元信息（时间戳/方向/耗时）

        self._build_ui()
        self._open_socket(port)

        # 批量刷新：40ms 合并一次，兼顾实时与流畅
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._flush_timer.start(40)

    # ---------- 界面 ----------
    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # 工具条
        bar = QHBoxLayout()
        bar.addWidget(QLabel("截断字节:"))
        self.spin_truncate = QSpinBox()
        self.spin_truncate.setRange(0, 4096)
        self.spin_truncate.setValue(self.truncate)
        self.spin_truncate.setToolTip("每行最多显示多少字节；0 = 全长显示")
        self.spin_truncate.valueChanged.connect(self._on_truncate_changed)
        bar.addWidget(self.spin_truncate)

        self.check_pause = QCheckBox("暂停")
        self.check_pause.toggled.connect(self._on_pause_toggled)
        bar.addWidget(self.check_pause)

        self.check_error = QCheckBox("只看异常")
        self.check_error.toggled.connect(self._on_error_toggled)
        bar.addWidget(self.check_error)

        self.check_autoscroll = QCheckBox("自动滚动")
        self.check_autoscroll.setChecked(True)
        bar.addWidget(self.check_autoscroll)

        self.check_ascii = QCheckBox("文本视图")
        self.check_ascii.setChecked(self.view == "ascii")
        self.check_ascii.setToolTip(
            "勾选：按 ASCII 显示（不可打印字符显示为 '.'）—— 看日志用\n"
            "不勾：按 HEX 显示 —— 看协议帧用")
        self.check_ascii.toggled.connect(self._on_ascii_toggled)
        bar.addWidget(self.check_ascii)

        self.check_assemble = QCheckBox("按行组装")
        self.check_assemble.setChecked(self.assemble)
        self.check_assemble.setEnabled(self.view == "ascii")
        self.check_assemble.setToolTip(
            "把被串口切碎的文本拼回整行（遇换行才输出）—— 仅在文本视图有效。\n"
            "串口没有消息边界，一条日志常被拆成多行显示；\n"
            "开启后同一行日志会合成一条。代价：要等到换行才刷新（最多 .3s）。")
        self.check_assemble.toggled.connect(self._on_assemble_toggled)
        bar.addWidget(self.check_assemble)

        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear)
        bar.addWidget(btn_clear)

        bar.addStretch(1)

        self.label_status = QLabel("监听 127.0.0.1:%d" % DEFAULT_UDP_PORT)
        self.label_status.setStyleSheet("color:#555;")
        bar.addWidget(self.label_status)
        layout.addLayout(bar)

        # 正文
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.setMaximumBlockCount(MAX_LINES)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        self.text.setFont(font)
        layout.addWidget(self.text, 1)

        # 输入框（预留：将来可从这里手动发帧）
        bottom = QHBoxLayout()
        self.line_input = QLineEdit()
        self.line_input.setPlaceholderText("（只读观察窗：暂不支持从窗口发帧）")
        self.line_input.setReadOnly(True)
        bottom.addWidget(self.line_input)
        layout.addLayout(bottom)

    # ---------- UDP ----------
    def _open_socket(self, port: int):
        self.sock = QUdpSocket(self)
        ok = self.sock.bind(QHostAddress("127.0.0.1"), port)
        if not ok:
            # 刻意不开 SO_REUSEADDR：它会让同机任意进程都能抢绑同一端口，
            # 是端口劫持风险。宁可让第二个窗口明确失败，也不要静默串流。
            self.label_status.setText(
                "绑定失败：端口 %d 已被占用 —— 通常是另一个监视窗口。"
                "本窗未在监听，收不到任何数据。可用 --port %d 换端口。"
                % (port, port + 1))
            self.label_status.setStyleSheet("color:#C62828;")
            self.label_status.setToolTip(
                "同一 UDP 端口不能被两个进程同时 bind。\n"
                "若要用两个窗口分别观察两条通道，请让两次 cli 分别广播到\n"
                "不同端口（cli --mirror-port N），窗口再各自 --port N。")
            return
        self.sock.readyRead.connect(self._on_ready_read)
        self.label_status.setText("监听 127.0.0.1:%d" % port)

    def _on_ready_read(self):
        while self.sock.hasPendingDatagrams():
            datagram = self.sock.receiveDatagram()
            raw = bytes(datagram.data())
            self._pkt_count += 1
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            evt = parse_event(line)
            if evt is not None:
                evt["seq"] = self._pkt_count
                self._pending.append(evt)

    # ---------- 渲染 ----------
    @staticmethod
    def _is_error(evt: dict) -> bool:
        """判定应答是否携带异常结果码。

        结果码只存在于数据域为 3 字节的应答（总长 13，文件传输/重构查询类）。
        先按帧内长度字段算出总长，只有确实是这类帧才去读下标 10；
        心跳等 12 字节应答的下标 10 是校验和高位，不得当作结果码。
        """
        if evt.get("dir") != "RX":
            return False
        data = bytes.fromhex(evt.get("hex", ""))
        if len(data) < HEAD_LEN + 2:
            return False
        # 总长由 [6:8] 的长度字段推出（值 = 数据域长度 - 1）
        total = HEAD_LEN + (int.from_bytes(data[6:8], "big") + 1) + 2
        if total != RESULT_FRAME_LEN or len(data) < RESULT_FRAME_LEN:
            return False
        return data[RESULT_BYTE_IDX] in ERROR_RESULTS

    def _render_body(self, data: bytes) -> str:
        """按当前视图渲染载荷。

        hex   —— 空格分隔的十六进制（协议帧）
        ascii —— 文本视图：只放行 ASCII 可见字符（0x20~0x7E）与 TAB，
                 其余（含 \\r \\n 与 0x80 以上的高位字节）显示为 '.'
        """
        if self.view == "ascii":
            # 必须逐字节判定，不能用 str.isprintable()：latin-1 解码会把
            # 0x80~0xFF 变成 U+0080~U+00FF，而 Python 认为这些"可打印"，
            # 二进制帧就会显示成 ÿÏ 之类的乱码字母而不是 '.'。
            return "".join(
                chr(b) if b == 0x09 or 0x20 <= b <= 0x7E else "."
                for b in data
            )
        return data.hex(" ")

    def _format(self, evt: dict):
        """把事件格式化成 (前缀, [ (文本, 颜色), ... ])。"""
        n = evt.get("n", 0)
        data = bytes.fromhex(evt.get("hex", ""))
        limit = self.spin_truncate.value()
        shown = data if limit == 0 else data[:limit]

        head = "%s  %s  %5dB  " % (
            evt.get("ts", ""),
            "TX →" if evt.get("dir") == "TX" else "RX ←",
            n,
        )
        body = self._render_body(shown)

        segments = [(head, COLOR_TX if evt.get("dir") == "TX" else COLOR_RX),
                    (body, QColor("#212121"))]

        if limit and n > limit:
            segments.append(("  ...(省略 %dB)" % (n - limit), COLOR_MUTED))

        el = evt.get("elapsed")
        if el is not None and el >= 0.05:
            segments.append(("  [%.3fs]" % el, COLOR_MUTED))

        if evt.get("note"):
            segments.append(("  %s" % evt["note"], COLOR_NOTE))

        if self._is_error(evt):
            segments = [(t, COLOR_ERROR) for (t, _) in segments]

        return segments

    def _flush_pending(self):
        if self.paused or not self._pending:
            return
        events, self._pending = self._pending, []

        sb = self.text.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4

        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = cursor.charFormat()

        for evt in self._emit_events(events):
            if self.only_error and not self._is_error(evt):
                continue
            for text, color in self._format(evt):
                fmt.setForeground(color)
                cursor.setCharFormat(fmt)
                cursor.insertText(text)
            cursor.setCharFormat(fmt)
            cursor.insertText("\n")
            self._line_count += 1

        if self.check_autoscroll.isChecked() and at_bottom:
            sb.setValue(sb.maximum())

        self.label_status.setText(
            "监听中[%s%s] · 收包 %d · 显示 %d 行 · 缓冲上限 %d"
            % (self.view, "+按行" if self.assemble else "",
               self._pkt_count, self._line_count, MAX_LINES))

    # ---------- 行组装 ----------
    def _emit_events(self, events):
        """按需把切碎的文本事件合成整行，逐个 yield 可渲染的事件 dict。

        ascii 视图默认开启：串口是字节流，一条日志常被拆成多次 read
        （实测 BL 日志按 1ms 一块刷，一句话跨 6 行）。这里把字节累积起来，
        遇 '\\n' 才产出一行。

        半行兜底：若距上次有新数据超过 ASSEMBLE_FLUSH 秒仍未见到换行，
        也强制吐出，避免内容一直不显示（例如日志行不带换行符）。
        """
        if not self.assemble:
            for evt in events:
                yield evt
            return

        for evt in events:
            self._asm_buf += bytes.fromhex(evt.get("hex", ""))
            if self._asm_meta is None:
                # 保留本行首段的时间戳/方向/耗时，后续段落只贡献字节
                self._asm_meta = evt
            while True:
                idx = self._asm_buf.find(b"\n")
                if idx < 0:
                    break
                chunk = bytes(self._asm_buf[:idx + 1])
                del self._asm_buf[:idx + 1]
                yield self._make_asm_event(chunk)
                self._asm_meta = evt if self._asm_buf else None

        # 超时兜底：缓冲区有残留且已静默过久 → 强制吐出
        if self._asm_buf and self._asm_meta is not None:
            last = self._asm_meta.get("wall", 0)
            import time as _t
            if last and (_t.time() - last) >= ASSEMBLE_FLUSH:
                chunk = bytes(self._asm_buf)
                self._asm_buf = bytearray()
                yield self._make_asm_event(chunk)
                self._asm_meta = None

    def _make_asm_event(self, data: bytes) -> dict:
        """用首段的元信息 + 组装后的完整字节，造一个可渲染事件。"""
        base = dict(self._asm_meta or {})
        base["hex"] = data.hex(" ")
        base["n"] = len(data)
        base["elapsed"] = None          # 拼接后耗时无意义，不显示
        base["note"] = base.get("note", "")
        base["assembled"] = True
        return base

    # ---------- 交互 ----------
    def _on_truncate_changed(self, value):
        self.spin_truncate.setValue(value)

    def _on_pause_toggled(self, checked):
        self.paused = bool(checked)

    def _on_error_toggled(self, checked):
        self.only_error = bool(checked)
        if not self.only_error:
            return
        # 切换过滤时重绘：清空后后续只保留异常（历史行不回溯筛选）
        self.text.clear()
        self._line_count = 0

    def _on_ascii_toggled(self, checked):
        """hex <-> ascii 切换。已显示的历史行不回溯重绘（本来就只是实时视图）。"""
        self.view = "ascii" if checked else "hex"
        # 行组装只在文本视图有意义
        self.check_assemble.setEnabled(self.view == "ascii")
        if self.view != "ascii":
            self.assemble = False
            self.check_assemble.setChecked(False)
            self._asm_buf = bytearray()
            self._asm_meta = None

    def _on_assemble_toggled(self, checked):
        self.assemble = bool(checked) and self.view == "ascii"
        if not self.assemble:
            # 关掉时丢弃半行残留，避免混入后续内容
            self._asm_buf = bytearray()
            self._asm_meta = None

    def _clear(self):
        self.text.clear()
        self._line_count = 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="watch_serial",
        description="串口流量监视窗口（只监听 UDP，不打开串口）")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT,
                        help="监听的 UDP 端口，默认 %d" % DEFAULT_UDP_PORT)
    parser.add_argument("--truncate", type=int, default=DEFAULT_TRUNCATE,
                        help="每行最多显示的字节数，0 = 全长，默认 %d" % DEFAULT_TRUNCATE)
    parser.add_argument("--view", choices=list(VIEWS), default=DEFAULT_VIEW,
                        help="载荷渲染：hex=字节流（协议帧）/ ascii=文本（日志），默认 %s"
                             % DEFAULT_VIEW)
    parser.add_argument("--title", default=None,
                        help='窗口标题，用于区分多个窗口，如 --title "COM1 self"')
    parser.add_argument("--assemble", dest="assemble", action="store_true",
                        default=None,
                        help="按行组装文本（遇换行才输出），仅 ascii 视图有效；"
                             "ascii 视图下默认开启")
    parser.add_argument("--no-assemble", dest="assemble", action="store_false",
                        help="关闭按行组装（每个读取块单独成行）")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    win = SerialMonitorWindow(port=args.port, truncate=args.truncate,
                              view=args.view, title=args.title,
                              assemble=args.assemble)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
