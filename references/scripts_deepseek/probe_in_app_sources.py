"""U4: 探测 DeepSeek App 内来源是否可见。

动作:
    提问一个会触发来源的问题 -> dump 回答页 XML -> 搜 http

判定准则:
    若有 URL -> 走 share-copy 路线 (抄豆包 source_links.py)
    若无 URL -> 走 CDP bridge 路线 (抄千问 source_extractor_bridge.py)

前置条件:
    - DeepSeek App 已登录
    - 用户已手动提问一个会触发来源的问题(如"今日新闻"), 并等待回答完成

用法:
    python scripts_deepseek/probe_in_app_sources.py --serial emulator-5556 \
        --output-dir outputs/deepseek/u4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mobile_auto_qianwen.adb_client import AdbClient
from mobile_auto_qianwen.constants import DEFAULT_ADB
from mobile_auto_qianwen.ui_xml import collect_nodes, extract_urls_from_text, visible_texts


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe whether DeepSeek exposes source URLs in-app.")
    parser.add_argument("--adb", default=DEFAULT_ADB)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--output-dir", default="outputs/deepseek/u4")
    args = parser.parse_args()

    adb = AdbClient(adb=args.adb, serial=args.serial)
    adb.resolve_serial()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("U4: DeepSeek in-app source URL probe")
    print("=" * 60)
    print("Precondition:")
    print("  1. DeepSeek App is open")
    print("  2. You have ASKED a question that triggers sources (e.g. '今日新闻')")
    print("  3. The answer has finished generating and sources are visible")
    input("Press Enter to dump current UI...")

    xml = adb.dump_xml()
    (output_dir / "answer_page.xml").write_text(xml, encoding="utf-8")
    nodes = collect_nodes(xml)

    # 扫描所有节点的 text/content_desc/resource_id 中的 URL
    all_urls: list[str] = []
    for node in nodes:
        for field in ("text", "content_desc", "resource_id"):
            val = node.get(field, "") or ""
            all_urls.extend(extract_urls_from_text(val))

    all_urls = list(dict.fromkeys(all_urls))
    texts = visible_texts(nodes)

    result = {
        "urls_found": all_urls,
        "url_count": len(all_urls),
        "visible_texts_sample": texts[:50],
    }
    (output_dir / "u4_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nURLs found in UI XML: {len(all_urls)}")
    for u in all_urls[:10]:
        print(f"  - {u}")

    print(f"\nvisible texts (top 20):")
    for t in texts[:20]:
        print(f"  - {t}")

    print("\n" + "=" * 60)
    if all_urls:
        print("[OK] In-app URLs found. Use share-copy route (copy from doubao).")
        print("    source_extraction_route = 'share_copy'")
        return 0
    print("[INFO] No URLs in UI XML. Use CDP bridge route (copy from qianwen).")
    print("    source_extraction_route = 'cdp_bridge'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
