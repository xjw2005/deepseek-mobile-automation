"""真机分步验证 DeepSeek 自动化核心函数。

按 todo 顺序逐步验证 ensure_app / detect_blocked / create_new_chat /
send_question + wait_for_answer（quick mode）/ thinking mode / share link。
每步打印结构化结果，失败即停止，便于定位。

用法:
    python scripts_deepseek/test_real_device_steps.py --step ensure
    python scripts_deepseek/test_real_device_steps.py --step newchat
    python scripts_deepseek/test_real_device_steps.py --step send
    python scripts_deepseek/test_real_device_steps.py --step thinking
    python scripts_deepseek/test_real_device_steps.py --step share
    python scripts_deepseek/test_real_device_steps.py --step all
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

from mobile_auto_deepseek.adb_client import AdbClient
from mobile_auto_deepseek.app import (
    capture_answer_page_thinking_content,
    create_new_chat,
    detect_blocked,
    dump_nodes,
    ensure_app,
    enter_thinking_mode,
    extract_answer_share_link,
    find_input_nodes,
    send_question,
    wait_for_answer,
)
from mobile_auto_deepseek.constants import DEFAULT_ADB


def make_adb(serial: str | None, adb_path: str = DEFAULT_ADB) -> AdbClient:
    client = AdbClient(adb=adb_path, serial=serial)
    client.resolve_serial()
    return client


def out_dir() -> str:
    d = ROOT / "outputs" / "deepseek-real-test"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def write_result(name: str, payload: dict) -> None:
    path = Path(out_dir(), f"{name}.json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[wrote] {path}")


def step_ensure(adb: AdbClient) -> dict:
    print("[step] ensure_app + detect_blocked")
    result = ensure_app(adb)
    nodes = dump_nodes(adb)
    blocked = detect_blocked(nodes)
    input_nodes = find_input_nodes(nodes)
    input_sample = {k: input_nodes[-1].get(k) for k in ("text", "class", "bounds", "resource_id")} if input_nodes else None
    payload = {"ensure": result, "blocked": blocked, "inputNodeCount": len(input_nodes), "inputNodeSample": input_sample}
    write_result("step-ensure", payload)
    return payload


def step_newchat(adb: AdbClient) -> dict:
    print("[step] create_new_chat", flush=True)
    try:
        result = create_new_chat(adb, out_dir(), save_debug_xml=True)
    except Exception as exc:
        import traceback
        result = {"error": str(exc), "traceback": traceback.format_exc()}
        print("[error] create_new_chat failed:", exc, flush=True)
    write_result("step-newchat", result)
    return result


def step_send(adb: AdbClient, question: str = "请用一句话解释什么是复利。") -> dict:
    print("[step] send_question + wait_for_answer (quick mode)")
    sent, send_debug = send_question(adb, question, out_dir())
    if not sent:
        payload = {"sent": False, "send": send_debug}
        write_result("step-send", payload)
        return payload
    answer_result = wait_for_answer(adb, question, out_dir(), timeout=120.0, stable_seconds=3)
    payload = {
        "sent": True,
        "send": send_debug,
        "answer": answer_result.get("answer", ""),
        "answerPreview": (answer_result.get("answer", "") or "")[:300],
        "samplesTail": answer_result.get("samples", [])[-3:],
    }
    write_result("step-send", payload)
    return payload


def step_thinking(adb: AdbClient, question: str = "请先深入思考，再用一句话说明复利为什么重要。") -> dict:
    print("[step] thinking mode + send + capture", flush=True)
    new_chat = create_new_chat(adb, out_dir(), save_debug_xml=True)
    mode = enter_thinking_mode(adb, out_dir())
    sent, send_debug = send_question(adb, question, out_dir())
    if not sent:
        payload = {"newChat": new_chat, "mode": mode, "sent": False, "send": send_debug}
        write_result("step-thinking", payload)
        return payload
    answer_result = wait_for_answer(adb, question, out_dir(), timeout=180.0, stable_seconds=3)
    capture = capture_answer_page_thinking_content(
        adb,
        out_dir(),
        question=question,
        max_scrolls=12,
        ocr_enabled=False,
    )
    payload = {
        "newChat": new_chat,
        "mode": mode,
        "sent": True,
        "send": send_debug,
        "answer": answer_result.get("answer", ""),
        "samplesTail": answer_result.get("samples", [])[-3:],
        "thinkingStatus": capture.get("status"),
        "thinkingContent": capture.get("content", ""),
        "thinkingRawContent": capture.get("rawContent", ""),
        "capture": {key: capture.get(key) for key in ("expansion", "snapshots", "detailOpen")},
    }
    write_result("step-thinking", payload)
    return payload


def step_share(adb: AdbClient) -> dict:
    print("[step] extract_answer_share_link")
    result = extract_answer_share_link(adb, out_dir())
    safe = {k: v for k, v in result.items() if k != "clipboardText"}
    write_result("step-share", safe)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Step-by-step real-device DeepSeek test.")
    parser.add_argument("--adb", default=DEFAULT_ADB)
    parser.add_argument("--serial", default="100.76.50.7:6666")
    parser.add_argument("--step", default="all", choices=["ensure", "newchat", "send", "thinking", "share", "all"])
    parser.add_argument("--question", default="请用一句话解释什么是复利。")
    args = parser.parse_args()

    adb = make_adb(args.serial, args.adb)
    print(f"device: {adb.serial}")

    if args.step == "ensure":
        step_ensure(adb)
        return 0
    # For all other steps, ensure_app first so DeepSeek is in foreground.
    step_ensure(adb)
    if args.step == "newchat":
        step_newchat(adb)
        return 0
    if args.step == "send":
        step_send(adb, args.question)
        return 0
    if args.step == "thinking":
        step_thinking(adb, args.question)
        return 0
    if args.step == "share":
        step_share(adb)
        return 0

    # all: 顺序执行
    r1 = step_ensure(adb)
    if r1["blocked"] or not r1["inputNodeCount"]:
        print("[abort] blocked or no input node")
        return 2
    r2 = step_newchat(adb)
    if not r2.get("created"):
        print("[abort] new chat failed")
        return 3
    r3 = step_send(adb, args.question)
    if not r3.get("answer"):
        print("[abort] no answer captured")
        return 4
    print("[done] quick-mode send+answer OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
