"""Debug: test send flow step by step with XML dumps."""
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mobile_auto_deepseek.adb_client import AdbClient
from mobile_auto_deepseek.app import (
    ensure_app, create_new_chat, focus_input, find_input_nodes,
    dump_nodes, tap_send_button, _ensure_text_mode, dump_xml,
    detect_blocked, visible_texts,
)
from mobile_auto_deepseek.constants import DEFAULT_ADB, ADB_KEYBOARD_IME

out = ROOT / "outputs" / "deepseek-real-test"
out.mkdir(parents=True, exist_ok=True)

def save_xml(adb, name):
    xml = adb.dump_xml()
    (out / name).write_text(xml, encoding="utf-8")
    print(f"  saved {name}", flush=True)

adb = AdbClient(adb=DEFAULT_ADB, serial="100.76.50.7:6666")
adb.resolve_serial()

print("1. ensure_app", flush=True)
ensure_app(adb)
save_xml(adb, "dbg-1-after-ensure.xml")

print("2. create_new_chat", flush=True)
create_new_chat(adb, str(out), save_debug_xml=False)
save_xml(adb, "dbg-2-after-newchat.xml")

print("3. check text mode + switch if needed", flush=True)
nodes = dump_nodes(adb)
switched = _ensure_text_mode(adb, nodes)
print(f"  switched to text mode: {switched}", flush=True)
if switched:
    time.sleep(0.5)
    save_xml(adb, "dbg-3-after-text-mode.xml")
    nodes = dump_nodes(adb)

print("4. focus input", flush=True)
focused = focus_input(adb, nodes)
print(f"  focused: {focused}", flush=True)
time.sleep(0.5)
save_xml(adb, "dbg-4-after-focus.xml")

print("5. set IME + type question", flush=True)
adb.set_ime(ADB_KEYBOARD_IME)
time.sleep(0.3)
question = "1+1=?"
adb.broadcast_base64_text(question)
time.sleep(1.5)
save_xml(adb, "dbg-5-after-type.xml")

print("6. check UI state after typing", flush=True)
nodes = dump_nodes(adb)
texts = visible_texts(nodes)
print(f"  visible texts: {texts[:15]}", flush=True)
# Check for send button
from mobile_auto_deepseek.app import _has_send_button
print(f"  has_send_button: {_has_send_button(nodes)}", flush=True)
# Print all clickable nodes in bottom area
for n in nodes:
    b = n.get("parsedBounds")
    if b and b["centerY"] > 1900 and n.get("clickable") == "true":
        print(f"  clickable: text={n.get('text','')!r} desc={n.get('content_desc','')!r} bounds={b}", flush=True)

print("7. tap send button", flush=True)
tapped = tap_send_button(adb, nodes)
print(f"  tapped: {tapped}", flush=True)
time.sleep(2.0)
save_xml(adb, "dbg-7-after-send.xml")

print("8. check if question was sent", flush=True)
nodes = dump_nodes(adb)
texts = visible_texts(nodes)
print(f"  visible texts: {texts[:20]}", flush=True)
