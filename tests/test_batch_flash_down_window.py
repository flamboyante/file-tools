import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FakeSignal:
    def __init__(self, *args, **kwargs):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)


class Dummy:
    def __init__(self, *args, **kwargs):
        self._text = ""
        self._items = []
        self._enabled = True
        self.clicked = FakeSignal()

    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def connect(self, *args, **kwargs):
        pass

    def addWidget(self, *args, **kwargs):
        pass

    def addLayout(self, *args, **kwargs):
        pass

    def setLayout(self, *args, **kwargs):
        pass

    def addItems(self, items):
        self._items.extend(items)

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setEnabled(self, enabled):
        self._enabled = enabled

    def isEnabled(self):
        return self._enabled


def install_stubs():
    pyqt5 = types.ModuleType("PyQt5")
    qtcore = types.ModuleType("PyQt5.QtCore")
    qtgui = types.ModuleType("PyQt5.QtGui")
    qtwidgets = types.ModuleType("PyQt5.QtWidgets")
    qtcore.Qt = types.SimpleNamespace(
        CopyAction=1,
        AlignCenter=0,
        UserRole=32,
        NoEditTriggers=0,
        SelectRows=1,
        SingleSelection=1,
        NonModal=0,
        Checked=2,
    )
    qtcore.QThread = Dummy
    qtcore.QTimer = Dummy
    qtcore.pyqtSignal = lambda *args, **kwargs: FakeSignal()
    qtgui.QColor = Dummy
    qtgui.QBrush = Dummy
    for name in [
        "QDialog",
        "QWidget",
        "QVBoxLayout",
        "QHBoxLayout",
        "QGridLayout",
        "QLabel",
        "QPushButton",
        "QTableWidget",
        "QTableWidgetItem",
        "QComboBox",
        "QLineEdit",
        "QCheckBox",
        "QProgressBar",
        "QTextEdit",
        "QFrame",
        "QHeaderView",
        "QFileDialog",
        "QAbstractItemView",
        "QMessageBox",
    ]:
        setattr(qtwidgets, name, Dummy)
    pyqt5.QtCore = qtcore
    pyqt5.QtGui = qtgui
    pyqt5.QtWidgets = qtwidgets
    sys.modules["PyQt5"] = pyqt5
    sys.modules["PyQt5.QtCore"] = qtcore
    sys.modules["PyQt5.QtGui"] = qtgui
    sys.modules["PyQt5.QtWidgets"] = qtwidgets

    serial_thread_mod = types.ModuleType("Serial_thread")
    serial_thread_mod.BatchFileTransfer_Work = Dummy
    sys.modules["Serial_thread"] = serial_thread_mod

    logging_mod = types.ModuleType("logging_config")
    logging_mod.log_print = lambda *args, **kwargs: None
    sys.modules["logging_config"] = logging_mod


install_stubs()

from UIClass.BatchFlashDownWindow import BatchDownloadTask, can_delete_task, can_edit_task, set_task_status


class BatchFlashDownWindowTaskTests(unittest.TestCase):
    def make_task(self, status="pending"):
        return BatchDownloadTask(
            file_path=os.path.join(ROOT, "test.bin"),
            file_size=12,
            flash_key="base",
            flash_value=0xFB,
            mem_key="app",
            mem_value=0x02,
            status=status,
        )

    def test_pending_rows_are_editable_and_deletable_until_globally_locked(self):
        task = self.make_task("pending")

        self.assertTrue(can_edit_task(task, globally_locked=False))
        self.assertTrue(can_delete_task(task, globally_locked=False))
        self.assertFalse(can_edit_task(task, globally_locked=True))

    def test_running_and_done_rows_are_fixed(self):
        for status in ["running", "done"]:
            task = self.make_task(status)

            self.assertFalse(can_edit_task(task, globally_locked=False))
            self.assertFalse(can_delete_task(task, globally_locked=False))

    def test_set_task_status_records_error_and_progress(self):
        task = self.make_task()

        set_task_status(task, "failed", error="boom", progress=34)

        self.assertEqual(task.status, "failed")
        self.assertEqual(task.error, "boom")
        self.assertEqual(task.progress, 34)


if __name__ == "__main__":
    unittest.main()
