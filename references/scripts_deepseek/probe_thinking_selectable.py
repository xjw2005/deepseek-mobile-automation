"""U5: 探测 DeepSeek 思考内容是否可选中文本。

动作:
    触发思考 -> 长按思考文本 -> 检查是否出现选择手柄 / selection 事件

判定准则:
    可选 -> 复用千问 capture_thinking_content 路线
    不可选 -> 启用 OCR 路线 (复用千问 ocr.py)

前置条件:
    - DeepSeek App 已登录
    - 用户已手动提问一个会触发深度思考的问题, 并展开思考详情页

用法:
    python scripts_deepseek/probe_thinking_selectable.py --serial emulator-5556 \
        --output-dir outputs/deepseek/u5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mobile_auto_qianwen.adb_client import AdbClient
from mobile_auto_qianwen.constants import DEFAULT_ADB
from mobile_auto_qianwen.ui_xml import collect_nodes, visible_texts


# 选择手柄相关 resource_id / class 关键词
SELECTION_HANDLE_KEYWORDS = (
    "selection_handle",
    "select_handle",
    "text_select_handle",
    "android.widget.SelectionHandleView",
)


def find_selection_handles(nodes: list[dict]) -> list[dict]:
    """查找选择手柄节点。"""
    hits = []
    for node in nodes:
        rid = node.get("resource_id", "") or ""
        cls = node.get("class", "") or ""
        combined = f"{rid} {cls}".lower()
        if any(kw in combined for kw in SELECTION_HANDLE_KEYWORDS):
            hits.append(node)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe whether DeepSeek thinking text is selectable.")
    parser.add_argument("--adb", default=DEFAULT_ADB)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--output-dir", default="outputs/deepseek/u5")
    args = parser.parse_args()

    adb = AdbClient(adb=args.adb, serial=args.serial)
    adb.resolve_serial()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("U5: DeepSeek thinking text selectability probe")
    print("=" * 60)
    print("Precondition:")
    print("  1. DeepSeek App is open")
    print("  2. You have asked a question that triggers deep thinking")
    print("  3. The thinking detail page is expanded and visible")
    input("Press Enter to dump current UI...")

    # 先 dump 一次基线
    xml_before = adb.dump_xml()
    (output_dir / "before_longpress.xml").write_text(xml_before, encoding="utf-8")
    nodes_before = collect_nodes(xml_before)
    handles_before = find_selection_handles(nodes_before)

    texts = visible_texts(nodes_before)
    print(f"\nvisible texts (top 20):")
    for t in texts[:20]:
        print(f"  - {t}")

    # 找一个文本节点做长按 (取屏幕中部第一个有 text 的节点)
    target = None
    for node in nodes_before:
        text = node.get("text", "")
        bounds = node.get("parsedBounds")
        if text and len(text) > 10 and bounds and 400 < bounds["centerY"] < 1800:
            target = node
            break

    if not target:
        print("\n[FAIL] No suitable text node for long-press test.")
        return 2

    bounds = target["parsedBounds"]
    print(f"\nLong-pressing text node at ({bounds['centerX']}, {bounds['centerY']})")
    print(f"  text preview: {target.get('text', '')[:60]!r}")

    adb.command([
        "shell", "input", "swipe",
        str(bounds["centerX"]), str(bounds["centerY"]),
        str(bounds["centerX"]), str(bounds["centerY"]),
        "1500",  # 长按 1.5s
    ])
    time.sleep(1.0)

    # dump 长按后的 UI
    xml_after = adb.dump_xml()
    (output_dir / "after_longpress.xml").write_text(xml_after, encoding="utf-8")
    nodes_after = collect_nodes(xml_after)
    handles_after = find_selection_handles(nodes_after)

    # 也检查是否出现"复制/全选/分享"等选择菜单
    selection_menu_keywords = ("复制", "全选", "选择", "分享", "Copy", "Select All")
    texts_after = visible_texts(nodes_after)
    menu_hits = [t for t in texts_after if any(kw in t for kw in selection_menu_keywords)]

    result = {
        "long_press_target": {
            "text": target.get("text", "")[:100],
            "bounds": target.get("bounds", ""),
        },
        "handles_before": len(handles_before),
        "handles_after": len(handles_after),
        "selection_menu_texts": menu_hits,
        "selectable": len(handles_after) > 0 or len(menu_hits) > 0,
    }
    (output_dir / "u5_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"selection handles before: {len(handles_before)}")
    print(f"selection handles after:  {len(handles_after)}")
    print(f"selection menu texts: {menu_hits}")

    if result["selectable"]:
        print("\n[OK] Thinking text is selectable. Use text_select route.")
        print("    thinking_capture_method = 'text_select'")
        return 0
    print("\n[INFO] Thinking text is NOT selectable. Use OCR route.")
    print("    thinking_capture_method = 'ocr'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
