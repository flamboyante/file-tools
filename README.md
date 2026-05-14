# JiangCan Tools

PyQt-based desktop utility for serial communication, CAN send/receive, firmware readback, and single/batch firmware refactor download.

## What Is Kept In Git

- Python source code and UI modules.
- Qt Designer `.ui` files and generated UI/resource Python files used by the app.
- Runtime images under `photo/`.
- CAN vendor DLL/lib files under `JiangCan_Tools/`, because the CAN window needs them on Windows.
- `Can_Frame_Deal/Can.xlsx`, because the CAN model reader loads this table at runtime.
- Unit tests under `tests/`.

## What Is Ignored

- Build/package outputs: `build/`, `dist/`, `*.exe`, archives.
- Logs and local runtime output.
- Firmware/readback binary files such as `*.bin` and `readflash*.bin`.
- Local IDE, cache, virtual environment, database, and exported spreadsheet files.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python FileFIle.py
```

Some optional screens import `siui`. If those screens are used, install the matching `siui` package/source used by this project.

## Validation

```powershell
python -m unittest discover tests
python -m py_compile FileFIle.py Serial_thread.py UIClass\BatchFlashDownWindow.py
```
