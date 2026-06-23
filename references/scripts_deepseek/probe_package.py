"""U3: 探测 DeepSeek App 包名。

判定准则:
    adb shell pm list packages | grep -i deepseek
    取唯一命中写入 DEEPSEEK_PACKAGE; 若多个命中则报错让人工确认。

用法:
    python scripts_deepseek/probe_package.py --serial emulator-5556
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mobile_auto_qianwen.adb_client import AdbClient
from mobile_auto_qianwen.constants import DEFAULT_ADB


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe DeepSeek Android package name.")
    parser.add_argument("--adb", default=DEFAULT_ADB)
    parser.add_argument("--serial", default=None)
    args = parser.parse_args()

    adb = AdbClient(adb=args.adb, serial=args.serial)
    adb.resolve_serial()

    # 列出所有包名, 过滤包含 deepseek 的
    output = adb.command(["shell", "pm", "list", "packages"]).stdout
    matches = []
    for line in (output or "").splitlines():
        line = line.strip()
        if line.startswith("package:"):
            name = line[len("package:"):].strip()
            if "deepseek" in name.lower():
                matches.append(name)

    print("=" * 60)
    print("U3: DeepSeek package probe")
    print("=" * 60)
    print(f"matched packages: {matches}")

    if len(matches) == 0:
        print("\n[FAIL] No package containing 'deepseek' found.")
        print("Action: Check whether DeepSeek App is installed, or adjust keyword.")
        return 2
    if len(matches) > 1:
        print("\n[AMBIGUOUS] Multiple packages matched. Manual confirmation required.")
        for m in matches:
            print(f"  - {m}")
        return 3

    pkg = matches[0]
    print(f"\n[OK] Single match: {pkg}")
    print("\nFill into mobile_auto_deepseek/constants.py:")
    print(f'    DEEPSEEK_PACKAGE = "{pkg}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
