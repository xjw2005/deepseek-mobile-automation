"""Debug: type text and inspect UI state for Compose UI."""
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mobile_auto_deepseek.adb_client import AdbClient
from mobile_auto_deepseek.app import (
    ensure_app, create_new_chat, focus_input, find_input_nodes,
    dump_nodes, _has_send_button, dump_xml,
)
from mobile_auto_deepseek.constants import DEFAULT_ADB, ADB_KEYBOARD_IME

out = ROOT / "outputs" / "deepseek-real-test"
out.mkdir(parents=True, exist_ok=True)

adb = AdbClient(adb=DEFAULT_ADB, serial="100.76.50.7:6666")
adb.resolve_serial()

print("ensure_app...", flush=True)
ensure_app(adb)
print("create_new_chat...", flush=True)
create_new_chat(adb, str(out), save_debug_xml=True)
print("focus_input...", flush=True)
nodes = dump_nodes(adb)
focused = focus_input(adb, nodes)
print("focused:", focused, flush=True)
time.sleep(0.5)

print("setting IME...", flush=True)
adb.set_ime(ADB_KEYBOARD_IME)
time.sleep(0.3)

print("broadcasting text...", flush=True)
question = "请用一句话解释什么是复利。"
adb.broadcast_base64_text(question)
time.sleep(1.5)

xml = adb.dump_xml()
(out / "debug-after-type.xml").write_text(xml, encoding="utf-8")
print("XML dumped", flush=True)

nodes = dump_nodes(adb)
print("input_nodes count:", len(find_input_nodes(nodes)), flush=True)
print("has_send_button:", _has_send_button(nodes), flush=True)

print("\n--- All clickable nodes in bottom area (y>1900) ---", flush=True)
for n in nodes:
    b = n.get("parsedBounds")
    if b and b["centerY"] > 1900:
        print(
            f"  clickable={n.get('clickable','')} "
            f"text={n.get('text','')!r} desc={n.get('content_desc','')!r} "
            f"class={n.get('class','')} bounds={b} pkg={n.get('package','')}",
            flush=True,
        )

print("\n--- All nodes with 发送/提交/完成 ---", flush=True)
for n in nodes:
    combined = n.get("text", "") + n.get("content_desc", "")
    if any(label in combined for label in ("发送", "提交", "完成")):
        b = n.get("parsedBounds")
        print(
            f"  clickable={n.get('clickable','')} text={n.get('text','')!r} "
            f"desc={n.get('content_desc','')!r} bounds={b}",
            flush=True,
        )
