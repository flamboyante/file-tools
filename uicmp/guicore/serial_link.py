# -*- coding: utf-8 -*-
"""serial_link · 串口链路门面（guicore 地基）。

════════════════════════════════════════════════════════════════
它解决什么
════════════════════════════════════════════════════════════════
旧实现（Serial_thread.py）的读是**阻塞式凑字节**：`media.recv(13)`
死等满 13 字节，等不到就永远挂住——所以旧窗口的「等应答」全都
绑死在 QThread 阻塞循环里，UI 和会话搅在一起。

本模块换成**事件驱动**：读线程常驻、来多少发多少（rx 信号），
发送走单一队列、整帧原子写出（多写者：传输帧 / 遥控 / 心跳排队，
字节流永不交错撕裂）。session 层订阅 rx 自己组帧——链路是哑管道。

422 的特殊性（一根物理线、transfer + rc 两个 session 共享）由
上层组合实现：两个 session 持有**同一个 SerialLink 实例**，
各自订阅 rx、各自调 send()。链路本身不为任何协议特化。

════════════════════════════════════════════════════════════════
线程模型（2 线程 + 门面）
════════════════════════════════════════════════════════════════
  _Reader(QThread)   serial.read(256, timeout=50ms) 阻塞式等数据
                      → 有数据再 drain inWaiting → emit rx(bytes)
  _Writer(QThread)   queue.get() 阻塞 → serial.write(整帧)
  SerialLink(QObject) 门面：open/close/send/状态信号

关闭顺序（不留僵尸线程）：先停标志 → 唤醒（reader 靠 read timeout
自然醒，writer 靠队列投毒 None）→ wait() → media.close()。

════════════════════════════════════════════════════════════════
依赖
════════════════════════════════════════════════════════════════
复用 Media.SerialMedia（本分支已补强：构造可传 timeout、is_open
不再被 finally 硬置 False）。pyserial 层异常全部转成 error 信号，
不向调用方抛——UI 拿信号渲染，回归测试拿信号断言。
"""
import queue
import threading

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from Media.SerialMedia import SerialMedia

# 默认串口参数（界面会给选择，这里只是兜底默认值）
DEF_BAUD = 115200
DEF_DATA_BITS = 8
DEF_STOP_BITS = 1
DEF_PARITY = 'N'

READ_TIMEOUT = 0.05      # 秒。读线程的「心跳」——也是 close 退出的最坏延迟
READ_CHUNK = 256

# 状态
ST_CLOSED = 'closed'
ST_OPEN = 'open'
ST_FAULT = 'fault'


class _Reader(QThread):
    """读线程：阻塞式等数据 + 排干。有数据就发，不等凑满。

    异常处理约定（对照 SerialMedia.recv 的 finally:return 教训——
    静默吞掉是那四个老 bug 之首）：读异常（拔线/重枚举）必须上报，
    不允许无声吞掉。同一波连续异常只报一次（streak 去重），恢复读取
    后清零——拔线时 UI 收到一条 error，而不是每 20ms 一条。
    """

    rx = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, media, parent=None):
        super(_Reader, self).__init__(parent)
        self._media = media
        self._running = True
        self._err_streak = False      # 是否正处于连续异常中

    def stop(self):
        self._running = False      # read timeout 到点后自然退出

    def run(self):
        ser = self._media.serial
        while self._running:
            try:
                data = ser.read(READ_CHUNK)       # timeout=50ms 自动醒
                if data:
                    extra = ser.inWaiting()
                    if extra:
                        data += ser.read(extra)
                    self.rx.emit(bytes(data))
                self._err_streak = False
            except Exception as e:
                if not self._err_streak:          # 每波只报一次
                    self._err_streak = True
                    self.failed.emit('读串口异常: %s' % e)
                self.msleep(50)
        # 清标志，让 close 后 run() 可安全重启（若复用线程对象）


class _Writer(QThread):
    """写线程：单一发送队列，整帧原子写出。

    队列元素是 bytes（一帧）。投毒 None = 退出哨兵。
    """

    tx_done = pyqtSignal(int)     # 实际写出的字节数
    failed = pyqtSignal(str)      # 写异常（帧丢失，调用方自行决定重发）

    def __init__(self, media, parent=None):
        super(_Writer, self).__init__(parent)
        self._media = media
        self._q = queue.Queue()
        self._running = True

    def put(self, frame):
        self._q.put(frame)

    def stop(self):
        self._q.put(None)          # 投毒唤醒

    def run(self):
        ser = self._media.serial
        while True:
            item = self._q.get()
            if item is None:
                break
            try:
                n = ser.write(item)
                self.tx_done.emit(int(n))
            except Exception as e:
                self.tx_done.emit(0)
                self.failed.emit('写串口异常（该帧丢失）: %s' % e)


class SerialLink(QObject):
    """串口链路门面。

    信号：
      opened()          打开成功
      closed()          已关闭（含故障后的关闭）
      error(str)        出错信息（打开失败 / 读写异常）
      rx(bytes)         收到原始字节（未组帧，session 层自己切）
      tx_done(int)      一帧写出完成（n=0 表示写失败）

    用法：
      link = SerialLink()
      link.rx.connect(...)               # 先订阅再打开
      link.open('COM7')                  # 或带全参数
      link.send(some_frame_bytes)        # 入队，线程里整帧写出
      link.close()
    """

    opened = pyqtSignal()
    closed = pyqtSignal()
    error = pyqtSignal(str)
    rx = pyqtSignal(bytes)
    tx_done = pyqtSignal(int)

    def __init__(self, parent=None):
        super(SerialLink, self).__init__(parent)
        self._media = None
        self._reader = None
        self._writer = None
        self.state = ST_CLOSED
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 状态
    @property
    def is_open(self):
        return self.state == ST_OPEN

    def _set_state(self, s):
        self.state = s

    # ------------------------------------------------------------ 开 / 关
    def open(self, port, baud=DEF_BAUD, data_bits=DEF_DATA_BITS,
             stop_bits=DEF_STOP_BITS, parity=DEF_PARITY, media=None):
        """打开链路。成功 → opened 信号 + state=OPEN；
        失败 → error 信号 + state=FAULT（或保持 CLOSED）。
        已打开时重复调用视为错误（不自动换口重开——界面应先 close）。

        media：注入已构造的 Media 对象（测试用假串口）；None 时现场构造
        SerialMedia。注入对象的 timeout 应为 READ_TIMEOUT。
        """
        with self._lock:
            if self.state == ST_OPEN:
                self.error.emit('链路已打开，请先关闭')
                return False
            try:
                if media is not None:
                    self._media = media
                    if not self._media.is_open:
                        self._media.open()
                else:
                    self._media = SerialMedia(
                        port=port, baud=baud, data_bits=data_bits,
                        stop_bits=stop_bits, parity=parity,
                        timeout=READ_TIMEOUT)
                    if not self._media.is_open:
                        self._media.open()
            except Exception as e:
                self._media = None
                self._set_state(ST_FAULT)
                self.error.emit('打开 %s 失败: %s' % (port, e))
                return False

            self._reader = _Reader(self._media)
            self._writer = _Writer(self._media)
            self._reader.rx.connect(self.rx)          # 透传（跨线程自动 queued）
            self._reader.failed.connect(self.error)   # 读异常上报（去重后）
            self._writer.tx_done.connect(self.tx_done)
            self._writer.failed.connect(self.error)
            self._reader.start()
            self._writer.start()
            self._set_state(ST_OPEN)
        self.opened.emit()
        return True

    def close(self):
        """关闭链路（幂等）。停线程 → 关串口 → closed 信号。"""
        with self._lock:
            if self.state != ST_OPEN:
                return
            self._set_state(ST_CLOSED)
            reader, writer, media = self._reader, self._writer, self._media
            self._reader = self._writer = self._media = None

        reader.stop()
        reader.wait(2000)
        writer.stop()
        writer.wait(2000)
        try:
            media.close()
        except Exception as e:
            self.error.emit('关闭串口异常: %s' % e)
        self.closed.emit()

    # ------------------------------------------------------------ 收 / 发
    def send(self, frame):
        """帧入发送队列（整帧原子写出，多写者安全）。

        返回 False 表示链路未打开（帧被丢弃，调用方自行提示）。
        """
        if self.state != ST_OPEN or self._writer is None:
            self.error.emit('链路未打开，发送被丢弃')
            return False
        self._writer.put(bytes(frame))
        return True

    # ------------------------------------------------------------ 清理
    def __del__(self):
        # 尽力而为：正常流程应由页面 close()
        try:
            if self.state == ST_OPEN:
                self.close()
        except Exception:
            pass
