"""U2: 探测 DeepSeek 分享链接形态。

动作:
    手动触发一次分享 -> 复制链接 -> 通过 paste-input 读取 URL

判定准则:
    若 URL 形如 https://chat.deepseek.com/share/... -> 写正则
    若 App 内无分享入口 -> 标记 share_link_supported = false

前置条件:
    - DeepSeek App 已登录并打开一个有回答的会话
    - 用户已手动点击"分享"按钮并触发"复制链接"(脚本只负责读取)

用法:
    python scripts_deepseek/probe_share_link.py --serial emulator-5556 \
        --output-dir outputs/deepseek/u2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mobile_auto_qianwen.adb_client import AdbClient
from mobile_auto_qianwen.constants import DEFAULT_ADB
from mobile_auto_qianwen.ui_xml import collect_nodes, extract_urls_from_text, find_nodes


# 可能的输入框 resource_id (探测时尽量宽松)
INPUT_ID_CANDIDATES = (
    "com.deepseek.chat:id/input_text",
    "com.deepseek.chat:id/et_input",
    "com.deepseek.chat:id/edit_text",
)


def find_input_node(nodes: list[dict]) -> dict | None:
    """找输入框节点。"""
    for rid in INPUT_ID_CANDIDATES:
        hits = find_nodes(nodes, resource_id=rid)
        if hits:
            return hits[-1]
    # 兜底: 找 EditText
    for node in nodes:
        if node.get("class") == "android.widget.EditText" and node.get("parsedBounds"):
            return node
    return None


def read_clipboard_via_paste(adb: AdbClient, output_dir: Path) -> dict:
    """通过粘贴到输入框读取剪贴板。"""
    xml = adb.dump_xml()
    (output_dir / "before_paste.xml").write_text(xml, encoding="utf-8")
    nodes = collect_nodes(xml)

    input_node = find_input_node(nodes)
    if not input_node:
        return {"ok": False, "error": "input_not_found"}

    bounds = input_node["parsedBounds"]
    adb.tap(bounds["centerX"], bounds["centerY"])
    time.sleep(0.3)

    # 清空输入框
    adb.keyevent(67)  # DEL
    time.sleep(0.1)

    # 粘贴 (KEYCODE_PASTE = 279)
    adb.keyevent(279)
    time.sleep(0.4)

    # 读取粘贴后的文本
    xml2 = adb.dump_xml()
    (output_dir / "after_paste.xml").write_text(xml2, encoding="utf-8")
    nodes2 = collect_nodes(xml2)

    pasted_text = ""
    urls: list[str] = []
    for node in find_nodes(nodes2, resource_id=input_node.get("resource_id", "")):
        text = node.get("text", "")
        if text:
            pasted_text = text
        urls.extend(extract_urls_from_text(text))

    # 兜底: 扫描所有 EditText
    if not urls:
        for node in nodes2:
            if node.get("class") == "android.widget.EditText":
                urls.extend(extract_urls_from_text(node.get("text", "")))

    return {
        "ok": True,
        "pasted_text": pasted_text,
        "urls": list(dict.fromkeys(urls)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe DeepSeek share link format.")
    parser.add_argument("--adb", default=DEFAULT_ADB)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--output-dir", default="outputs/deepseek/u2")
    args = parser.parse_args()

    adb = AdbClient(adb=args.adb, serial=args.serial)
    adb.resolve_serial()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("U2: DeepSeek share link probe")
    print("=" * 60)
    print("Precondition:")
    print("  1. DeepSeek App is open with an answered conversation")
    print("  2. You have MANUALLY tapped Share -> Copy link on a message")
    print("  3. Now press Enter to let this script read the clipboard")
    input("Press Enter when ready...")

    result = read_clipboard_via_paste(adb, output_dir)
    print(f"\npaste result: {result}")

    urls = result.get("urls", [])
    (output_dir / "u2_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    if not urls:
        print("[FAIL] No URL found in clipboard.")
        print("Action: Verify share/copy flow, or set share_link_supported = False")
        return 2

    url = urls[0]
    print(f"[OK] Found URL: {url}")

    # 推断正则
    # 通用化: 把具体 ID 替换为 [A-Za-z0-9]+
    pattern = re.sub(r"/[A-Za-z0-9_-]{6,}(?=\?|$)", "/[A-Za-z0-9_-]+", url)
    pattern = re.escape(pattern).replace(re.escape("[A-Za-z0-9_-]+"), "[A-Za-z0-9_-]+")
    # 进一步放宽 host
    pattern = re.sub(r"chat\\\.deepseek\\\.com", r"(chat\\.)?deepseek\\\.com", pattern)

    print("\nFill into constants.py:")
    print(f'    DEEPSEEK_SHARE_URL_RE_PATTERN = r"^{pattern}"')
    print("    share_link_supported = True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
