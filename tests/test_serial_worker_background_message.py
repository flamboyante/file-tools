import os
import sys
import types
import importlib
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


class FakeQThread:
    def __init__(self, parent=None):
        self.parent = parent

    def msleep(self, ms):
        pass


class FakeQTimer:
    def __init__(self, parent=None):
        self.parent = parent
        self.timeout = FakeSignal()
        self.started_with = None
        self.stop_called = False

    def start(self, interval):
        self.started_with = interval
        self.stop_called = False

    def stop(self):
        self.stop_called = True


class FakeMediaType:
    SERIAL = "serial"
    ETHERNET = "ethernet"
    VLAN = "vlan"


class FakeSerialMedia:
    def __init__(self, *args, **kwargs):
        self.is_open = False
        self.sent = []
        self.close_called = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False
        self.close_called = True

    def send(self, data):
        self.sent.append(data)
        return len(data)


class FakeEthernetMedia(FakeSerialMedia):
    pass


class FakeVlanMedia(FakeSerialMedia):
    pass


def install_stubs():
    pyqt5 = types.ModuleType("PyQt5")
    qtcore = types.ModuleType("PyQt5.QtCore")
    qtcore.QThread = FakeQThread
    qtcore.QTimer = FakeQTimer
    qtcore.QMutex = object
    qtcore.QWaitCondition = object
    qtcore.pyqtSignal = lambda *args, **kwargs: FakeSignal()
    pyqt5.QtCore = qtcore
    sys.modules["PyQt5"] = pyqt5
    sys.modules["PyQt5.QtCore"] = qtcore

    media_pkg = types.ModuleType("Media")
    media_mod = types.ModuleType("Media.Media")
    media_mod.Media = object
    media_mod.MediaType = FakeMediaType
    serial_media_mod = types.ModuleType("Media.SerialMedia")
    serial_media_mod.SerialMedia = FakeSerialMedia
    ethernet_mod = types.ModuleType("Media.EthernetMedia")
    ethernet_mod.EthernetMedia = FakeEthernetMedia
    vlan_mod = types.ModuleType("Media.VlanMedia")
    vlan_mod.VlanMedia = FakeVlanMedia
    sys.modules["Media"] = media_pkg
    sys.modules["Media.Media"] = media_mod
    sys.modules["Media.SerialMedia"] = serial_media_mod
    sys.modules["Media.EthernetMedia"] = ethernet_mod
    sys.modules["Media.VlanMedia"] = vlan_mod

    ycyk_mod = types.ModuleType("ycyk_422")

    class FakeYcykWork:
        def __init__(self, *args, **kwargs):
            pass

    ycyk_mod.Ycyk_422_Work = FakeYcykWork
    sys.modules["ycyk_422"] = ycyk_mod

    logging_mod = types.ModuleType("logging_config")
    logging_mod.log_print = lambda *args, **kwargs: None
    sys.modules["logging_config"] = logging_mod

    serial_mod = types.ModuleType("serial")
    serial_mod.PARITY_NONE = "N"
    serial_mod.PARITY_EVEN = "E"
    serial_mod.PARITY_ODD = "O"
    serial_mod.STOPBITS_ONE = 1
    serial_mod.STOPBITS_TWO = 2
    serial_mod.STOPBITS_ONE_POINT_FIVE = 1.5
    sys.modules["serial"] = serial_mod


install_stubs()
sys.modules.pop("Serial_thread", None)
serial_thread = importlib.import_module("Serial_thread")


class SerialWorkerBackgroundMessageTests(unittest.TestCase):
    def test_background_payload_matches_expected_hex(self):
        expected = bytes.fromhex(
            "EB 90 01 80 C0 00 00 26 00 01 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 FE 97"
        )

        self.assertEqual(serial_thread.FIXED_BACKGROUND_PAYLOAD, expected)

    def test_opening_serial_starts_background_timer(self):
        worker = serial_thread.Serial_Worker()

        worker.init_media(FakeMediaType.SERIAL, "COM1", 115200, 8, "1", "NONE")

        self.assertEqual(worker.status, 1)
        self.assertIsNotNone(worker.fixed_message_timer)
        self.assertEqual(worker.fixed_message_timer.started_with, 1000)

    def test_closing_serial_stops_background_timer(self):
        worker = serial_thread.Serial_Worker()
        worker.init_media(FakeMediaType.SERIAL, "COM1", 115200, 8, "1", "NONE")

        worker.close_serial()

        self.assertTrue(worker.fixed_message_timer.stop_called)

    def test_background_message_uses_same_media_instance(self):
        worker = serial_thread.Serial_Worker()
        worker.media = FakeSerialMedia()
        worker.media.open()
        worker.status = 1
        worker.fixed_message_timer = FakeQTimer()

        worker.send_fixed_background_message()

        self.assertEqual(worker.media.sent[-1], serial_thread.FIXED_BACKGROUND_PAYLOAD)


class RecordingBatchWorker(serial_thread.BatchFileTransfer_Work):
    def __init__(self, *args, fail_on=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_on = fail_on
        self.calls = []
        self.sleeps = []

    def execute_transfer_task(self, task):
        self.calls.append(task.file_path)
        if task.file_path == self.fail_on:
            raise RuntimeError("boom")

    def msleep(self, ms):
        self.sleeps.append(ms)


class BatchFileTransferWorkTests(unittest.TestCase):
    def make_task(self, file_path):
        return types.SimpleNamespace(
            file_path=file_path,
            flash_value=0xFB,
            mem_value=0x05,
            status="pending",
            error="",
        )

    def test_batch_worker_runs_tasks_in_order_with_interval(self):
        statuses = []
        worker = RecordingBatchWorker(
            FakeSerialMedia(),
            [self.make_task("a.bin"), self.make_task("b.bin")],
            divide=True,
            frame_len=1000,
            frame_num=1024,
            interval_ms=1000,
        )
        worker.task_status_signal.connect(lambda index, status, error: statuses.append((index, status, error)))

        worker.run()

        self.assertEqual(worker.calls, ["a.bin", "b.bin"])
        self.assertEqual(worker.sleeps, [1000])
        self.assertIn((0, "done", ""), statuses)
        self.assertIn((1, "done", ""), statuses)

    def test_batch_worker_stops_after_first_failure(self):
        statuses = []
        worker = RecordingBatchWorker(
            FakeSerialMedia(),
            [self.make_task("a.bin"), self.make_task("bad.bin"), self.make_task("c.bin")],
            divide=True,
            frame_len=1000,
            frame_num=1024,
            interval_ms=1000,
            fail_on="bad.bin",
        )
        worker.task_status_signal.connect(lambda index, status, error: statuses.append((index, status, error)))

        worker.run()

        self.assertEqual(worker.calls, ["a.bin", "bad.bin"])
        self.assertIn((1, "failed", "boom"), statuses)
        self.assertIn((2, "skipped", ""), statuses)


if __name__ == "__main__":
    unittest.main()
