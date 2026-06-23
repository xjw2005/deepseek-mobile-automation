"""U1: 探测 DeepSeek 思考模式 UI 路径。

动作:
    启动 App -> dump 首页 XML -> 搜索文本 "深度思考/思考/联网搜索/推理"

判定准则:
    若找到可点击开关节点 -> 记录其 resource_id / text / bounds,
        写入 THINK_BUTTON_TEXT 与(若有) THINK_BUTTON_ID
    若无开关 -> 标记 thinking_supported = false

用法:
    python scripts_deepseek/probe_thinking_entry.py --serial emulator-5556 \
        --package com.deepseek.app --output-dir outputs/deepseek/u1
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
from mobile_auto_qianwen.ui_xml import collect_nodes, find_nodes, visible_texts


CANDIDATE_TEXTS = ("深度思考", "思考", "联网搜索", "推理", "DeepThink", "Think")
VIEW_ALL_CANDIDATES = ("查看全部", "展开全部", "全部思考", "查看思考")


def find_toggles(nodes: list[dict]) -> list[dict]:
    """找出包含候选文本且可点击的节点。"""
    hits = []
    for node in nodes:
        text = (node.get("text", "") + " " + node.get("content_desc", "")).strip()
        if not text:
            continue
        if not any(kw in text for kw in CANDIDATE_TEXTS):
            continue
        bounds = node.get("parsedBounds")
        if not bounds:
            continue
        hits.append({
            "text": text,
            "resource_id": node.get("resource_id", ""),
            "clickable": node.get("clickable", ""),
            "bounds": node.get("bounds", ""),
            "centerX": bounds["centerX"],
            "centerY": bounds["centerY"],
        })
    return hits


def find_view_all(nodes: list[dict]) -> list[dict]:
    """找出查看全部类节点。"""
    hits = []
    for node in nodes:
        text = (node.get("text", "") + " " + node.get("content_desc", "")).strip()
        if not text:
            continue
        if not any(kw in text for kw in VIEW_ALL_CANDIDATES):
            continue
        bounds = node.get("parsedBounds")
        if not bounds:
            continue
        hits.append({
            "text": text,
            "resource_id": node.get("resource_id", ""),
            "clickable": node.get("clickable", ""),
            "bounds": node.get("bounds", ""),
        })
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe DeepSeek thinking-mode UI entry.")
    parser.add_argument("--adb", default=DEFAULT_ADB)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--package", required=True, help="DeepSeek package name (run probe_package.py first).")
    parser.add_argument("--output-dir", default="outputs/deepseek/u1")
    args = parser.parse_args()

    adb = AdbClient(adb=args.adb, serial=args.serial)
    adb.resolve_serial()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 启动 App
    print(f"[U1] Launching {args.package} ...")
    adb.start_app(args.package)
    time.sleep(2.5)

    # dump 首页
    xml = adb.dump_xml()
    (output_dir / "home.xml").write_text(xml, encoding="utf-8")
    nodes = collect_nodes(xml)
    texts = visible_texts(nodes)

    print("=" * 60)
    print("U1: DeepSeek thinking-mode entry probe")
    print("=" * 60)
    print(f"visible texts (top 30):")
    for t in texts[:30]:
        print(f"  - {t}")

    toggles = find_toggles(nodes)
    view_all = find_view_all(nodes)

    print(f"\ntoggle candidates: {len(toggles)}")
    for t in toggles:
        print(f"  - text={t['text']!r} id={t['resource_id']!r} clickable={t['clickable']} "
              f"center=({t['centerX']},{t['centerY']})")

    print(f"\nview-all candidates: {len(view_all)}")
    for v in view_all:
        print(f"  - text={v['text']!r} id={v['resource_id']!r} clickable={v['clickable']}")

    result = {
        "package": args.package,
        "thinking_supported": len(toggles) > 0,
        "toggles": toggles,
        "view_all_candidates": view_all,
        "visible_texts_sample": texts[:50],
    }
    (output_dir / "u1_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    if toggles:
        primary = toggles[0]
        print("[OK] Thinking toggle found. Fill into constants.py:")
        print(f'    THINK_BUTTON_TEXT = "{primary["text"]}"')
        if primary["resource_id"]:
            print(f'    THINK_BUTTON_ID = "{primary["resource_id"]}"')
        else:
            print('    THINK_BUTTON_ID = ""  # no resource_id, use text fallback')
        if view_all:
            print(f'    VIEW_ALL_TEXT = "{view_all[0]["text"]}"')
        print("    thinking_supported = True")
        return 0
    print("[INFO] No thinking toggle found on home page.")
    print("Action: Manually trigger a question that invokes thinking, then re-run.")
    print("    thinking_supported = False  # if confirmed unsupported")
    return 1


if __name__ == "__main__":
    sys.exit(main())
