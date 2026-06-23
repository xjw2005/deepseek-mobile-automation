"""U6: 探测 DeepSeek 分享页是否需要登录。

动作:
    CDP 打开分享页 -> 检查是否跳登录页

判定准则:
    不需要 -> 直接抄千问 run.js 流程
    需要 -> bridge 必须支持 cookie 注入 (在 ADR 第 9 节"后续工作"中追踪)

前置条件:
    - 本机已启动 Chrome/Chromium 并开启 --remote-debugging-port=9222
    - 已通过 U2 探测拿到一个 DeepSeek 分享链接

用法:
    python scripts_deepseek/probe_share_page_auth.py --url <share_url> \
        --cdp-url http://127.0.0.1:9222 --output-dir outputs/deepseek/u6
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


LOGIN_INDICATORS = (
    "login", "登录", "sign in", "signin", "账号登录",
    "手机号", "验证码", "扫码登录", "二维码",
    "password", "密码",
)


def list_cdp_targets(cdp_url: str) -> list[dict]:
    """通过 CDP /json 接口列出所有页面目标。"""
    url = cdp_url.rstrip("/") + "/json"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else []


def open_via_cdp(cdp_url: str, target_url: str) -> dict:
    """通过 CDP /json/new 接口打开一个新页面。"""
    url = cdp_url.rstrip("/") + "/json/new?" + target_url
    req = urllib.request.Request(url, method="PUT")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def close_cdp_target(cdp_url: str, target_id: str) -> None:
    """关闭一个 CDP 目标。"""
    url = cdp_url.rstrip("/") + f"/json/close/{target_id}"
    try:
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe whether DeepSeek share page requires login.")
    parser.add_argument("--url", required=True, help="DeepSeek share URL (from U2 probe).")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--output-dir", default="outputs/deepseek/u6")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("U6: DeepSeek share page auth probe")
    print("=" * 60)
    print(f"CDP URL: {args.cdp_url}")
    print(f"Share URL: {args.url}")

    # 1. 检查 CDP 是否可用
    try:
        targets = list_cdp_targets(args.cdp_url)
    except Exception as exc:
        print(f"\n[FAIL] Cannot reach CDP endpoint: {exc}")
        print("Action: Launch Chrome with --remote-debugging-port=9222 first.")
        return 2

    print(f"\nexisting CDP targets: {len(targets)}")

    # 2. 通过 CDP 打开分享页
    print(f"\nOpening share URL via CDP ...")
    try:
        new_target = open_via_cdp(args.cdp_url, args.url)
    except Exception as exc:
        print(f"[FAIL] Cannot open URL via CDP: {exc}")
        return 3

    target_id = new_target.get("id", "")
    final_url = new_target.get("url", "")
    title = new_target.get("title", "")
    print(f"new target id: {target_id}")
    print(f"final url:     {final_url}")
    print(f"title:         {title}")

    # 3. 判定是否需要登录
    # 简化判定: 检查最终 URL 与 title 是否含登录关键词
    # 完整判定需要 CDP 抓 DOM, 这里用 title/url 做初判
    combined = f"{final_url} {title}".lower()
    requires_auth = any(kw.lower() in combined for kw in LOGIN_INDICATORS)

    # 也检查 url 是否被重定向到登录页
    redirected_to_login = (
        "/login" in final_url.lower()
        or "/signin" in final_url.lower()
        or "/account" in final_url.lower()
    )

    requires_auth = requires_auth or redirected_to_login

    result = {
        "share_url": args.url,
        "final_url": final_url,
        "title": title,
        "requires_auth": requires_auth,
        "redirected_to_login": redirected_to_login,
    }
    (output_dir / "u6_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 关闭目标
    if target_id:
        close_cdp_target(args.cdp_url, target_id)

    print("\n" + "=" * 60)
    if requires_auth:
        print("[INFO] Share page requires login.")
        print("    share_page_requires_auth = True")
        print("Action: bridge must support cookie injection (see ADR section 9).")
        return 1
    print("[OK] Share page does NOT require login.")
    print("    share_page_requires_auth = False")
    print("Action: Copy qianwen run.js flow directly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
