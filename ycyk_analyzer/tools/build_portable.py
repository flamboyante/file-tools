# -*- coding: utf-8 -*-
"""
build_portable.py —— 打「绿色分发包」：嵌入式 Python + 代码 + 外置解析表。

产出一个文件夹，拷到任何 Win10/11 机器上双击 `启动.bat` 就能用，
**目标机不需要装 Python**。

用法:
    python tools/build_portable.py [输出目录]
    默认输出到仓库的 dist/ycyk_cli/

包结构:
    ycyk_cli/
      启动.bat          <- 双击它（也可以把数据文件夹直接拖到它身上）
      spec/             <- **外置解析表**：现场改判据只改这里，不必重新打包
      app/              <- 代码
      python/           <- 嵌入式解释器 + openpyxl

设计要点:
  * 表放在**包根**而不是 app/ 里 —— 现场人员最容易找到并替换
  * 解释器与代码分开放，包看起来不像"一堆散文件"
  * `启动.bat` 全 ASCII，中文提示统一交给 cli.py 输出
    （bat 文件本身带中文会踩 cmd 的 GBK / UTF-8 编码坑）
  * 体积约 17 MB，对比主程序 FileFIle 打包产物 327 MB
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.dirname(HERE)              # ycyk_analyzer/
REPO_DIR = os.path.dirname(PKG_DIR)          # 仓库根

PY_VERSION = "3.8.10"
PY_ZIP_URLS = [
    "https://mirrors.huaweicloud.com/python/{v}/python-{v}-embed-amd64.zip",
    "https://registry.npmmirror.com/-/binary/python/{v}/python-{v}-embed-amd64.zip",
    "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip",
]

SPEC_FILE = "spec_merged_20260914.xlsx"

# 打进包里的代码（tools/ 是开发工具，不进去）
CODE_FILES = [
    "cli.py", "batch.py", "report.py", "judge.py", "spec.py",
    "frame.py", "t_segment.py", "table_csv.py", "bitfield.py", "align.py", "probe.py",
]

# 唯一第三方依赖 openpyxl —— 注意它依赖 et_xmlfile，**漏拷就跑不起来**
SITE_PACKAGES = ("openpyxl", "et_xmlfile")
SITE_DIR = r"D:\Anaconda3\envs\pyqt_side_all_0328\Lib\site-packages"

START_BAT = r"""@echo off
chcp 65001 > nul
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0app\cli.py" %*
echo.
echo ============================================================
echo  Done. Press any key to close this window.
echo ============================================================
pause > nul
"""


def log(msg: str) -> None:
    print(msg)


def fetch_python(py_dir: str) -> None:
    """下载并解压嵌入式 Python（已存在就跳过，省得重复下载）。"""
    if os.path.isfile(os.path.join(py_dir, "python.exe")):
        log("[跳过] 嵌入式 Python 已存在：{}".format(py_dir))
        return

    os.makedirs(py_dir, exist_ok=True)
    zip_path = os.path.join(py_dir, "_embed.zip")
    last_error = None

    for template in PY_ZIP_URLS:
        url = template.format(v=PY_VERSION)
        try:
            log("[下载] {}".format(url))
            urllib.request.urlretrieve(url, zip_path)
            break
        except Exception as exc:
            last_error = exc
            log("       失败（{}），换下一个源".format(exc.__class__.__name__))
    else:
        raise SystemExit("所有下载源都失败，最后一个错误：{}".format(last_error))

    log("[解压] {} -> {}".format(os.path.basename(zip_path), py_dir))
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(py_dir)
    os.remove(zip_path)


def write_pth(py_dir: str) -> None:
    """改 python38._pth：把包内的 Lib\\site-packages 加进搜索路径。

    ⚠️ 这里**故意不打开 `import site`**（embeddable 包里那行默认是注释掉的）。
    打开它会把用户级的 `%APPDATA%\\Python\\Python38\\site-packages` 也拉进 sys.path，
    目标机若装过 Python 就可能加载到别人的包、撞版本。只加包内路径才能保证完全自包含。

    不改这个文件，`import openpyxl` 必然失败。
    """
    path = os.path.join(py_dir, "python38._pth")
    content = (
        "python38.zip\n"
        ".\n"
        "Lib\\site-packages\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    log("[配置] python38._pth -> 只加包内路径（不开 site，避免污染目标机）")


def copy_packages(py_dir: str) -> None:
    target = os.path.join(py_dir, "Lib", "site-packages")
    os.makedirs(target, exist_ok=True)
    for pkg in SITE_PACKAGES:
        src = os.path.join(SITE_DIR, pkg)
        if not os.path.isdir(src):
            raise SystemExit("找不到依赖包：{}（检查 SITE_DIR 配置）".format(src))
        dst = os.path.join(target, pkg)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        log("[拷贝] 依赖 {}".format(pkg))


def copy_code(app_dir: str) -> None:
    os.makedirs(app_dir, exist_ok=True)
    missing = [f for f in CODE_FILES if not os.path.isfile(os.path.join(PKG_DIR, f))]
    if missing:
        raise SystemExit("缺少代码文件：{}".format("、".join(missing)))
    for name in CODE_FILES:
        shutil.copy(os.path.join(PKG_DIR, name), os.path.join(app_dir, name))
    log("[拷贝] 代码 {} 个文件 -> app\\".format(len(CODE_FILES)))


def copy_spec(spec_dir: str) -> None:
    os.makedirs(spec_dir, exist_ok=True)
    src = os.path.join(PKG_DIR, "spec", SPEC_FILE)
    if not os.path.isfile(src):
        raise SystemExit("找不到解析表：{}".format(src))
    shutil.copy(src, os.path.join(spec_dir, SPEC_FILE))
    log("[拷贝] 外置解析表 -> spec\\{}".format(SPEC_FILE))


def write_bat(dist_dir: str) -> None:
    path = os.path.join(dist_dir, "启动.bat")
    with open(path, "w", encoding="ascii", newline="\r\n") as fh:
        fh.write(START_BAT)
    log("[生成] 启动.bat")


def cleanup(dist_dir: str) -> None:
    """清掉 __pycache__，让包干净些。"""
    removed = 0
    for root, dirs, _files in os.walk(dist_dir):
        for name in list(dirs):
            if name == "__pycache__":
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
                dirs.remove(name)
                removed += 1
    if removed:
        log("[清理] 删除 {} 个 __pycache__".format(removed))


def dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def main() -> None:
    dist_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_DIR, "dist", "ycyk_cli")
    dist_dir = os.path.abspath(dist_dir)
    py_dir = os.path.join(dist_dir, "python")
    app_dir = os.path.join(dist_dir, "app")
    spec_dir = os.path.join(dist_dir, "spec")

    log("=" * 70)
    log("打绿色分发包 -> {}".format(dist_dir))
    log("=" * 70)

    fetch_python(py_dir)
    write_pth(py_dir)
    copy_packages(py_dir)
    copy_code(app_dir)
    copy_spec(spec_dir)
    write_bat(dist_dir)
    cleanup(dist_dir)

    log("=" * 70)
    log("完成。体积 %.1f MB" % (dir_size(dist_dir) / 1048576.0))
    log("自测：cd 到包目录后跑")
    log('  python\\python.exe app\\cli.py --spec-info')
    log("=" * 70)


if __name__ == "__main__":
    main()
