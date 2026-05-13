import re

import serial
from PyQt5.QtCore import QTimer
from PyQt5.QtSerialPort import QSerialPortInfo
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from Media.SerialMedia import SerialMedia
from logging_config import log_print


BAUD_RATES = ["115200", "9600", "921600", "4000000", "2000000"]
DATA_BITS = ["8", "7", "6"]
STOP_BITS = ["1", "1.5", "2"]
PARITY_BITS = ["NONE", "ODD", "EVEN"]

PARITY_MAP = {
    "NONE": serial.PARITY_NONE,
    "ODD": serial.PARITY_ODD,
    "EVEN": serial.PARITY_EVEN,
}

STOP_BITS_MAP = {
    "1": serial.STOPBITS_ONE,
    "1.5": serial.STOPBITS_ONE_POINT_FIVE,
    "2": serial.STOPBITS_TWO,
}


def parse_hex_payload(text: str) -> bytes:
    normalized = re.sub(r"\s+", "", text or "")
    normalized = re.sub(r"0[xX]", "", normalized)
    if not normalized:
        raise ValueError("hex data is empty")
    if not re.fullmatch(r"[0-9a-fA-F]+", normalized):
        raise ValueError("hex data contains invalid characters")
    if len(normalized) % 2 != 0:
        raise ValueError("hex data length must be even")
    return bytes.fromhex(normalized)


class SerialPortController:
    def __init__(self, index, log_callback, media_factory=SerialMedia, timer=None):
        self.index = index
        self.log_callback = log_callback
        self.media_factory = media_factory
        self.media = None
        self.is_open = False
        self.is_timing = False
        self.payload_provider = None
        self.timer = timer or QTimer()
        self.timer.timeout.connect(self._handle_timer_timeout)

    def open(self, port, baud_rate, data_bits, stop_bits, parity):
        if not port:
            raise ValueError("serial port is empty")
        stop_bit = STOP_BITS_MAP.get(str(stop_bits))
        parity_bit = PARITY_MAP.get(str(parity))
        if stop_bit is None:
            raise ValueError(f"invalid stop bits: {stop_bits}")
        if parity_bit is None:
            raise ValueError(f"invalid parity: {parity}")

        self.media = self.media_factory(port, int(baud_rate), int(data_bits), stop_bit, parity_bit)
        self.media.open()
        self.is_open = True
        self.log(f"opened {port}")

    def close(self):
        self.stop_timer()
        if self.media is not None and self.media.is_open:
            self.media.close()
        self.is_open = False
        self.log("closed")

    def send_once(self, payload_text):
        if not self.is_open or self.media is None or not self.media.is_open:
            raise RuntimeError("serial port is not open")
        payload = parse_hex_payload(payload_text)
        written = self.media.send(payload)
        self.log(f"sent {written} bytes")
        return written

    def start_timer(self, interval_ms, payload_provider):
        interval = int(interval_ms)
        if interval <= 0:
            raise ValueError("interval must be greater than 0")
        if not self.is_open:
            raise RuntimeError("serial port is not open")
        parse_hex_payload(payload_provider())
        self.payload_provider = payload_provider
        self.timer.start(interval)
        self.is_timing = True
        self.log(f"timer started: {interval} ms")

    def stop_timer(self):
        self.timer.stop()
        self.is_timing = False
        self.log("timer stopped")

    def _handle_timer_timeout(self):
        try:
            self.send_once(self.payload_provider())
        except Exception as exc:
            self.stop_timer()
            self.log(f"timer stopped by error: {exc}")

    def log(self, message):
        self.log_callback(f"Serial {self.index}: {message}")


class SerialSendWindow(QDialog):
    SLOT_COUNT = 4

    def __init__(self, parent=None):
        super(SerialSendWindow, self).__init__(parent)
        self.setWindowTitle("Serial Send")
        self.resize(1180, 520)
        self.controllers = []
        self.rows = []
        self._build_ui()

        self.port_refresh_timer = QTimer()
        self.port_refresh_timer.timeout.connect(self.refresh_ports)
        self.port_refresh_timer.start(1000)
        self.refresh_ports()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        group_box = QGroupBox("Serial ports")
        grid = QGridLayout(group_box)

        headers = [
            "#",
            "COM",
            "Baud",
            "Data",
            "Stop",
            "Parity",
            "Hex data",
            "Period(ms)",
            "State",
            "Open",
            "Send",
            "Timer",
        ]
        for column, title in enumerate(headers):
            grid.addWidget(QLabel(title), 0, column)

        for row_index in range(1, self.SLOT_COUNT + 1):
            controller = SerialPortController(row_index, self.append_log)
            row = self._create_row(row_index, controller)
            self.controllers.append(controller)
            self.rows.append(row)
            self._add_row_widgets(grid, row_index, row)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        root_layout.addWidget(group_box)
        root_layout.addWidget(self.log_edit)

    def _create_row(self, index, controller):
        row = {
            "label": QLabel(str(index)),
            "port": QComboBox(),
            "baud": QComboBox(),
            "data_bits": QComboBox(),
            "stop_bits": QComboBox(),
            "parity": QComboBox(),
            "payload": QLineEdit(),
            "interval": QLineEdit("1000"),
            "state": QLabel("closed"),
            "open_button": QPushButton("Open"),
            "send_button": QPushButton("Send"),
            "timer_button": QPushButton("Start"),
        }
        row["baud"].addItems(BAUD_RATES)
        row["data_bits"].addItems(DATA_BITS)
        row["stop_bits"].addItems(STOP_BITS)
        row["parity"].addItems(PARITY_BITS)
        row["payload"].setPlaceholderText("EB 90 01 02")

        row["open_button"].clicked.connect(lambda checked=False, r=row, c=controller: self.toggle_open(r, c))
        row["send_button"].clicked.connect(lambda checked=False, r=row, c=controller: self.send_once(r, c))
        row["timer_button"].clicked.connect(lambda checked=False, r=row, c=controller: self.toggle_timer(r, c))
        return row

    def _add_row_widgets(self, grid, row_index, row):
        widgets = [
            row["label"],
            row["port"],
            row["baud"],
            row["data_bits"],
            row["stop_bits"],
            row["parity"],
            row["payload"],
            row["interval"],
            row["state"],
            row["open_button"],
            row["send_button"],
            row["timer_button"],
        ]
        for column, widget in enumerate(widgets):
            grid.addWidget(widget, row_index, column)

    def refresh_ports(self):
        ports = [port.portName() for port in QSerialPortInfo.availablePorts()]
        for row in self.rows:
            combo = row["port"]
            current = combo.currentText()
            combo.clear()
            combo.addItems(ports)
            if current in ports:
                combo.setCurrentText(current)

    def toggle_open(self, row, controller):
        try:
            if controller.is_open:
                controller.close()
                row["state"].setText("closed")
                row["open_button"].setText("Open")
                row["timer_button"].setText("Start")
            else:
                controller.open(
                    row["port"].currentText(),
                    row["baud"].currentText(),
                    row["data_bits"].currentText(),
                    row["stop_bits"].currentText(),
                    row["parity"].currentText(),
                )
                row["state"].setText("open")
                row["open_button"].setText("Close")
        except Exception as exc:
            row["state"].setText("error")
            self.append_log(f"Serial {controller.index}: open/close failed: {exc}")

    def send_once(self, row, controller):
        try:
            controller.send_once(row["payload"].text())
            row["state"].setText("open")
        except Exception as exc:
            row["state"].setText("error")
            self.append_log(f"Serial {controller.index}: send failed: {exc}")

    def toggle_timer(self, row, controller):
        try:
            if controller.is_timing:
                controller.stop_timer()
                row["state"].setText("open" if controller.is_open else "closed")
                row["timer_button"].setText("Start")
            else:
                controller.start_timer(row["interval"].text(), row["payload"].text)
                row["state"].setText("timing")
                row["timer_button"].setText("Stop")
        except Exception as exc:
            row["state"].setText("error")
            row["timer_button"].setText("Start")
            self.append_log(f"Serial {controller.index}: timer failed: {exc}")

    def append_log(self, text):
        try:
            self.log_edit.append(text)
        except Exception:
            log_print(text)

    def closeEvent(self, event):
        for controller in self.controllers:
            try:
                controller.close()
            except Exception as exc:
                log_print(f"serial send window close failed: {exc}")
        super(SerialSendWindow, self).closeEvent(event)
