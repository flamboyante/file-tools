import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self):
        for slot in list(self._slots):
            slot()


class FakeTimer:
    def __init__(self):
        self.timeout = FakeSignal()
        self.started_with = None
        self.stop_count = 0

    def start(self, interval):
        self.started_with = interval

    def stop(self):
        self.stop_count += 1


class FakeMedia:
    instances = []

    def __init__(self, port, baud, data_bits, stop_bits, parity):
        self.port = port
        self.baud = baud
        self.data_bits = data_bits
        self.stop_bits = stop_bits
        self.parity = parity
        self.is_open = False
        self.sent = []
        FakeMedia.instances.append(self)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def send(self, data):
        self.sent.append(data)
        return len(data)


def install_stubs():
    pyqt5 = types.ModuleType("PyQt5")
    qtcore = types.ModuleType("PyQt5.QtCore")
    qtserial = types.ModuleType("PyQt5.QtSerialPort")
    qtwidgets = types.ModuleType("PyQt5.QtWidgets")

    class Dummy:
        def __init__(self, *args, **kwargs):
            self._text = ""
            self._items = []
            self.clicked = FakeSignal()

        def __getattr__(self, name):
            return self

        def addWidget(self, *args, **kwargs):
            pass

        def addLayout(self, *args, **kwargs):
            pass

        def addItems(self, items):
            self._items.extend(items)

        def setText(self, text):
            self._text = text

        def text(self):
            return self._text

        def currentText(self):
            return self._text or (self._items[0] if self._items else "")

        def setCurrentText(self, text):
            self._text = text

        def clear(self):
            self._items = []

        def append(self, *args, **kwargs):
            pass

    qtcore.QTimer = FakeTimer
    qtcore.Qt = types.SimpleNamespace(NonModal=0)
    qtserial.QSerialPortInfo = types.SimpleNamespace(availablePorts=lambda: [])
    for name in [
        "QDialog",
        "QHBoxLayout",
        "QVBoxLayout",
        "QGridLayout",
        "QLabel",
        "QLineEdit",
        "QComboBox",
        "QPushButton",
        "QTextEdit",
        "QGroupBox",
        "QWidget",
    ]:
        setattr(qtwidgets, name, Dummy)

    pyqt5.QtCore = qtcore
    pyqt5.QtSerialPort = qtserial
    pyqt5.QtWidgets = qtwidgets
    sys.modules["PyQt5"] = pyqt5
    sys.modules["PyQt5.QtCore"] = qtcore
    sys.modules["PyQt5.QtSerialPort"] = qtserial
    sys.modules["PyQt5.QtWidgets"] = qtwidgets

    serial_mod = types.ModuleType("serial")
    serial_mod.PARITY_NONE = "N"
    serial_mod.PARITY_EVEN = "E"
    serial_mod.PARITY_ODD = "O"
    serial_mod.STOPBITS_ONE = 1
    serial_mod.STOPBITS_TWO = 2
    serial_mod.STOPBITS_ONE_POINT_FIVE = 1.5
    sys.modules["serial"] = serial_mod

    serial_media_mod = types.ModuleType("Media.SerialMedia")
    serial_media_mod.SerialMedia = FakeMedia
    sys.modules["Media.SerialMedia"] = serial_media_mod

    logging_mod = types.ModuleType("logging_config")
    logging_mod.log_print = lambda *args, **kwargs: None
    sys.modules["logging_config"] = logging_mod


install_stubs()

from UIClass.SerialSendWindow import SerialPortController, parse_hex_payload


class SerialSendWindowTests(unittest.TestCase):
    def setUp(self):
        FakeMedia.instances = []
        self.logs = []

    def test_parse_hex_payload_accepts_common_formats(self):
        self.assertEqual(parse_hex_payload("EB 90 01 02"), bytes.fromhex("EB900102"))
        self.assertEqual(parse_hex_payload("EB900102"), bytes.fromhex("EB900102"))
        self.assertEqual(parse_hex_payload("0xEB 0x90 0x01 0x02"), bytes.fromhex("EB900102"))

    def test_parse_hex_payload_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            parse_hex_payload("")
        with self.assertRaises(ValueError):
            parse_hex_payload("EB 9")
        with self.assertRaises(ValueError):
            parse_hex_payload("EB ZZ")

    def test_controller_opens_sends_and_closes_one_port(self):
        timer = FakeTimer()
        controller = SerialPortController(1, self.logs.append, media_factory=FakeMedia, timer=timer)

        controller.open("COM1", 115200, 8, "1", "NONE")
        sent = controller.send_once("EB 90")
        controller.close()

        media = FakeMedia.instances[0]
        self.assertEqual(media.port, "COM1")
        self.assertEqual(media.baud, 115200)
        self.assertEqual(media.sent, [bytes.fromhex("EB90")])
        self.assertEqual(sent, 2)
        self.assertFalse(controller.is_open)

    def test_controller_timer_sends_latest_payload_and_stops_on_bad_input(self):
        timer = FakeTimer()
        payloads = ["EB 90", "bad"]
        controller = SerialPortController(2, self.logs.append, media_factory=FakeMedia, timer=timer)
        controller.open("COM2", 9600, 8, "1", "NONE")

        controller.start_timer(250, lambda: payloads[0])
        timer.timeout.emit()
        payloads[0] = payloads[1]
        timer.timeout.emit()

        media = FakeMedia.instances[0]
        self.assertEqual(timer.started_with, 250)
        self.assertEqual(media.sent, [bytes.fromhex("EB90")])
        self.assertGreaterEqual(timer.stop_count, 1)
        self.assertFalse(controller.is_timing)


if __name__ == "__main__":
    unittest.main()
