# -*- coding: utf-8 -*-
"""
cli.py —— ycyk 遥测分析工具的**唯一入口**。

用法:
    python cli.py <数据目录>              批量：解析目录下所有 快遥/慢遥 CSV，出一份总览
    python cli.py <csv> [<csv2>]          单组：解析 1~2 个 CSV，出一份报告
    python cli.py --spec-info             只显示当前用的是哪个解析表（含指纹），不解析数据

选项:
    -o, --out <文件>     输出 xlsx（默认自动命名，放在数据旁边）
    --spec <文件>        指定解析表（默认自动搜索，**外置优先** —— 见 spec.py）
    --log <文件>         日志文件（默认放在输出旁边，叫 ycyk_run.log）

退出码:
    0 成功 / 1 用法或数据有问题 / 2 意外异常

设计要点（都是给"现场没人能帮你调试"这件事准备的）:
  * 输出目录不可写（只读 U 盘、网络共享）时**自动回退**到程序目录，不让人卡在一半
  * 所有控制台输出**同时落日志** —— 出了事有据可查
  * 打包成绿色包后，把 `spec/` 放在 exe 旁边就能改判据，不必重新打包
  * 出错给一句人话提示 + 非零退出码，避免双击时"一闪而过什么都没看到"
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from typing import List, Optional

try:                                    # Windows 控制台默认 GBK，转 UTF-8 免得中文乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 绿色分发包里代码放在 app\ 子目录下：嵌入式 Python 有 ._pth 文件时会隔离 sys.path，
# 这里显式把本文件所在目录加进去，保证同目录的 spec / batch / report 能导入。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from spec import default_spec_path, spec_fingerprint, spec_search_dirs  # noqa: E402

LOG_NAME = "ycyk_run.log"


class UserError(Exception):
    """用法或数据本身的问题 —— 只需要一句人话提示，不用堆 traceback。"""


# ---------------------------------------------------------------------------
# 日志：把控制台输出一分为二
# ---------------------------------------------------------------------------


class TeeStream:
    """把写操作同时送往多个流（控制台 + 日志文件）。"""

    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]

    def write(self, text):
        for stream in self._streams:
            try:
                stream.write(text)
            except Exception:
                pass
        return len(text) if text else 0

    def flush(self):
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:
                pass

    def __getattr__(self, name):        # isatty / encoding 之类透传给第一个流
        return getattr(self._streams[0], name)


def attach_log(log_path: str) -> None:
    """开始把控制台输出同时写进日志；日志开不了就只留屏幕，不影响正事。"""
    try:
        handle = open(log_path, "w", encoding="utf-8")
    except Exception as exc:
        print("[提示] 日志文件打不开（{}），只在屏幕上显示：{}".format(
            exc.__class__.__name__, log_path))
        return
    sys.stdout = TeeStream(sys.__stdout__, handle)


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------


def program_dir() -> str:
    """程序所在目录 —— 打包后是 exe 目录，开发态是本文件所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def default_out_path(target: str) -> str:
    """默认输出名：目录 → 「批量总览_<目录名>.xlsx」；CSV → 「<名>_判据.xlsx」。

    都放在**数据旁边** —— 现场最直观：分析完，结果就在数据隔壁。
    """
    target = os.path.abspath(target)
    if os.path.isdir(target):
        stamp = os.path.basename(target.rstrip("\\/")) or "batch"
        return os.path.join(os.path.dirname(target), "批量总览_{}.xlsx".format(stamp))
    base = os.path.splitext(os.path.basename(target))[0]
    return os.path.join(os.path.dirname(target), base + "_判据.xlsx")


def ensure_writable(out_path: str, fallback_dir: str) -> str:
    """确认输出目录真能写；不能写就退到 fallback_dir。

    现场数据常放在只读 U 盘或网络共享上，直接写会抛异常、白跑一遍，
    所以这里**先探一下**再决定输出位置。
    """
    parent = os.path.dirname(os.path.abspath(out_path)) or "."
    try:
        if not os.path.isdir(parent):
            os.makedirs(parent)
        probe = os.path.join(parent, ".ycyk_write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.remove(probe)
        return out_path
    except Exception:
        fallback = os.path.join(fallback_dir, os.path.basename(out_path))
        print("[提示] 输出目录不可写：{}".format(parent))
        print("       改为写到：{}".format(fallback))
        return fallback


def _progress(done: int, total: int, name: str) -> None:
    """批量进度回调：每 5 组 + 最后一组打一行，免得现场以为程序卡死了。"""
    if done == total or done % 5 == 0:
        print("  [{}/{}] {}".format(done, total, name))


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(
        prog="ycyk",
        description="ycyk 遥测（快遥 / 慢遥）解析 + 判据分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  ycyk D:\\数据\\0914                        批量：分析整个目录\n"
            "  ycyk 快遥-0914-00.csv 慢遥1-0914-00.csv    单组：快慢合一出一份\n"
            "  ycyk D:\\数据\\0914 -o D:\\结果\\0914.xlsx   指定输出位置\n"
        ),
    )
    parser.add_argument("inputs", nargs="*", metavar="路径",
                        help="一个数据目录（批量），或 1~2 个 CSV 文件（单组）")
    parser.add_argument("-o", "--out", metavar="文件", help="输出 xlsx（默认放在数据旁边）")
    parser.add_argument("--spec", metavar="文件",
                        help="解析表 xlsx（默认自动搜索，外置优先）")
    parser.add_argument("--log", metavar="文件",
                        help="日志文件（默认放在输出旁边）")
    parser.add_argument("--spec-info", action="store_true",
                        help="只显示当前用的解析表与指纹，不解析数据")
    return parser.parse_args(argv)


def show_spec_info(spec_path: str) -> int:
    print("解析表搜索顺序（第一个存在的生效）：")
    for idx, folder in enumerate(spec_search_dirs(), start=1):
        print("  {}. {}{}spec{}".format(idx, folder, os.sep, os.sep))
    print()
    print("当前使用：{}".format(spec_path))
    print("指纹    ：{}".format(spec_fingerprint(spec_path)))
    exists = os.path.isfile(spec_path)
    print("文件存在：{}".format("是" if exists else "否  <-- 表不在这里，先把它放过去"))
    return 0 if exists else 1


def _is_interactive() -> bool:
    """是不是在真控制台里跑（双击 bat 的场景）—— 管道 / 重定向时不要抢输入。"""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _ask_for_input() -> List[str]:
    """没带参数时问一句要分析哪里 —— 双击 `启动.bat` 的人就靠这一步。"""
    print("没给数据路径。两种做法都行：")
    print()
    print("  1) 把数据文件夹（或 CSV 文件）拖到「启动.bat」图标上，再松手")
    print("  2) 在下面粘贴或输入路径，回车确认")
    print()
    try:
        raw = input("数据路径: ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print()
        return []
    return [raw] if raw else []


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    spec_path = os.path.abspath(args.spec) if args.spec else default_spec_path()

    if args.spec_info:
        return show_spec_info(spec_path)

    if not args.inputs:
        if _is_interactive():
            args.inputs = _ask_for_input()
        if not args.inputs:
            print("没给数据路径。用 --help 看用法，例如：")
            print("  ycyk D:\\数据\\0914")
            return 1

    # ---- 输入校验：目录（批量）还是 CSV（单组）----
    paths = [os.path.abspath(p) for p in args.inputs]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise UserError("路径不存在：\n  " + "\n  ".join(missing))

    dirs = [p for p in paths if os.path.isdir(p)]
    files = [p for p in paths if os.path.isfile(p)]

    if dirs and files:
        raise UserError("不能混着给：要么一个目录（批量），要么 CSV 文件（单组）")
    if len(dirs) > 1:
        raise UserError("一次只能批量处理一个目录，当前给了 {} 个".format(len(dirs)))
    if len(files) > 2:
        raise UserError("一次最多两个 CSV（快遥 + 慢遥），当前给了 {} 个".format(len(files)))

    if not os.path.isfile(spec_path):
        raise UserError(
            "找不到解析表：{}\n"
            "请把 spec_merged_*.xlsx 放到程序目录的 spec{} 下，或用 --spec 指定。".format(
                spec_path, os.sep))

    target = dirs[0] if dirs else files[0]

    # ---- 输出位置 + 日志 ----
    out_path = os.path.abspath(args.out) if args.out else default_out_path(target)
    out_path = ensure_writable(out_path, program_dir())

    log_path = os.path.abspath(args.log) if args.log else os.path.join(
        os.path.dirname(out_path) or program_dir(), LOG_NAME)
    attach_log(log_path)

    try:
        print("=" * 78)
        print("ycyk 遥测分析")
        print("  输入  : {}".format(target))
        print("  输出  : {}".format(out_path))
        print("  判据表: {}".format(spec_fingerprint(spec_path)))
        print("=" * 78)
        print()

        # 业务模块延迟导入：--spec-info 之类的诊断路径不必把它们拉进来
        if dirs:
            import batch
            batch.run_batch(target, out_path, progress=_progress, spec_path=spec_path)
        else:
            import report
            report.build_report(files, out_path, spec_path=spec_path)
    finally:
        sys.stdout.flush()

    print()
    print("[完成] 结果：{}".format(out_path))
    print("       日志：{}".format(log_path))
    return 0


def run(argv: Optional[List[str]] = None) -> int:
    """包一层异常处理：现场双击运行时，至少能看清出了什么事。"""
    try:
        return main(argv)
    except UserError as exc:
        print()
        print("[错误] {}".format(exc))
        return 1
    except KeyboardInterrupt:
        print()
        print("[中断] 已取消")
        return 1
    except Exception:
        print()
        print("[错误] 意外异常，以下为详细信息：")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(run())
