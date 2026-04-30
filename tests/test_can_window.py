import os
import sys
import types
import unittest
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def install_pyqt_stubs():
    if "PyQt5" in sys.modules:
        return

    pyqt5 = types.ModuleType("PyQt5")
    qtcore = types.ModuleType("PyQt5.QtCore")
    qtgui = types.ModuleType("PyQt5.QtGui")
    qtwidgets = types.ModuleType("PyQt5.QtWidgets")

    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, name):
            return self

        def connect(self, *args, **kwargs):
            pass

        def setSingleShot(self, *args, **kwargs):
            pass

        def start(self, *args, **kwargs):
            pass

        def stop(self, *args, **kwargs):
            pass

        def append(self, *args, **kwargs):
            pass

        def setDisabled(self, *args, **kwargs):
            pass

        def setEnabled(self, *args, **kwargs):
            pass

        def setText(self, *args, **kwargs):
            pass

    qtcore.QTimer = _Dummy
    qtcore.QThread = _Dummy
    qtcore.pyqtSignal = lambda *args, **kwargs: _Dummy()
    qtcore.Qt = types.SimpleNamespace(Checked=2, NonModal=0)
    qtwidgets.QDialog = type("QDialog", (object,), {})
    qtwidgets.QMessageBox = _Dummy

    pyqt5.QtCore = qtcore
    pyqt5.QtGui = qtgui
    pyqt5.QtWidgets = qtwidgets

    sys.modules["PyQt5"] = pyqt5
    sys.modules["PyQt5.QtCore"] = qtcore
    sys.modules["PyQt5.QtGui"] = qtgui
    sys.modules["PyQt5.QtWidgets"] = qtwidgets


install_pyqt_stubs()

from JiangCan_Tools.CanWindow import CanWindow


class DummySender:
    def __init__(self):
        self.frames = []

    def send(self, frame):
        self.frames.append(frame)


class CanWindowStarWgs84Tests(unittest.TestCase):
    def test_ui_source_contains_star_wgs84_controls_with_default_interval(self):
        ui_source = Path(ROOT, "JiangCan_Tools", "can_ui.py").read_text(encoding="utf-8")

        self.assertIn("self.checkBox_star_wgs84", ui_source)
        self.assertIn("self.lineEdit_star_wgs84", ui_source)
        self.assertIn('"STAR_WGS84"', ui_source)
        self.assertIn('self.lineEdit_star_wgs84.setText(_translate("CanForm", "1000"))', ui_source)

    def test_send_msg_for_star_wgs84_test_sends_same_frame_to_can_a_and_b(self):
        can_a = DummySender()
        can_b = DummySender()
        fake_window = types.SimpleNamespace(can_send=can_a, can_send_b=can_b)

        CanWindow.send_msg_for_star_wgs84_test(fake_window)

        self.assertEqual(len(can_a.frames), 1)
        self.assertEqual(len(can_b.frames), 1)

        frame_a = can_a.frames[0]
        frame_b = can_b.frames[0]

        self.assertEqual(frame_a.name, "STAR_WGS84")
        self.assertEqual(frame_b.name, "STAR_WGS84")
        self.assertEqual(frame_a.data[:4], [0x00, 0x23, 0x00, 0x04])
        self.assertEqual(frame_b.data[:4], [0x00, 0x23, 0x00, 0x04])
        self.assertEqual(frame_a.data, frame_b.data)


if __name__ == "__main__":
    unittest.main()
