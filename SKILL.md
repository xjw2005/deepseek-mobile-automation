---
name: deepseek-mobile-automation
description: Drives DeepSeek Android via ADB to capture answers/share links, extracts real source URLs via a Node.js CDP script, and writes to Feishu. Invoke for DeepSeek mobile runs or share-page source extraction. NEW v2.1: --link-only mode skips mobile thinking capture, fetches all content from desktop share page API in ~3 sec. --feishu-config externalizes the Feishu answer/source table IDs into a JSON (switch environments without source edits).
---

# DeepSeek Mobile Automation

Use this skill to run, debug, or migrate the DeepSeek mobile automation integration on another machine.
It covers two cooperating modules: a Python runner that drives the DeepSeek Android app, and a Node.js extractor that pulls real source URLs, answer text, and thinking content from DeepSeek share pages via Chrome DevTools Protocol.

**v2.0 Update**: New `--link-only` mode skips slow mobile thinking capture (2–5 min) and fetches all content from the desktop share page API (~3 sec). Ideal for high-volume collection runs.

## Two Modules

1. **DeepSeek来源提取 (DeepSeek Source Extractor)** — Node.js script under `references/deepseek-source-extractor/` and `references/mobile-auto-deepseek/deepseek-source-extractor/`. It connects to Chrome via CDP, replays the share/content API from the page context, and extracts:
   - **Answer text** (full, not viewport-truncated)
   - **Thinking content** (when deep-thinking was enabled)
   - **Real article URLs and metadata** (title, platform, snippet, publish time, site icon)
   - **Metadata**: thinking elapsed time, search enablement, message count
   
   It can write sources directly to a Feishu Bitable or export as JSON.

2. **跑移动端 (DeepSeek Mobile Runner)** — Python package under `references/mobile-auto-deepseek/mobile_auto_deepseek/`. It drives the DeepSeek Android app via ADB: opens chats, types questions with ADB Keyboard, waits for answers, and (optionally, in **normal mode**) captures deep-thinking content via mobile scroll+OCR. Always taps the share button to copy the share link. With `--extract-sources`, it invokes the JS extractor to pull content and sources from the share page API.

   **NEW in v2.0:** Use `--link-only` to skip mobile thinking capture entirely. The runner will fetch answer, thinking, and sources from the share page API (~3 sec instead of 2–5 min per question).

The Python runner is the orchestrator. With `--extract-sources` and `--link-only`, it captures the share URL on mobile, then hands off all content extraction to the JS extractor running against the desktop share page.

## Core Workflow

1. Read `references/README.md` before setup, ADB/device changes, Chrome CDP setup, or Feishu Base changes.
2. Restore `references/mobile-auto-deepseek/` into a workspace if the project is not already present. The workspace must contain `mobile_auto_deepseek/` (Python package) and `deepseek-source-extractor/` (JS scripts) as siblings.
3. Confirm prerequisites: Android device online, ADB Keyboard set as IME, Chrome running with `--remote-debugging-port=9222`, `lark-cli` on PATH, Node.js installed.
4. Run `python -m mobile_auto_deepseek.runner --task <task.json> --dry-run` before any live run.
5. Use a unique `--output` for each parallel process.
6. Use live runs only when an Android device is online, the DeepSeek app is already logged in, and (for `--extract-sources`) Chrome has the target share page open.
7. **For high-volume runs**, use `--link-only --extract-sources --writeback` to skip mobile thinking capture and fetch all content from the desktop share page API. This reduces per-question time from ~2–5 min to ~30 sec (30 sec for answer completion wait + 3 sec for API extraction).
8. After each run, report the output path, status counts, answer text, `thinkingContent`, `answerShareUrl`, source titles, source URLs, and any blocked/partial/failed reasons.

Deep-thinking toggle semantics are deliberately conservative: only a literal boolean `thinking: true` may change the DeepSeek UI. Missing values, `null`, and `false` leave the app's current toggle state untouched. Before force-enabling, the runner reads the toggle parent's UIAutomator attributes (`checkable="true"`, `checked="true|false"`); it skips the tap when already enabled and verifies `checked="true"` after a tap.

ADB calls are bounded: each subprocess has a 15-second timeout. Read-only commands retry once by default, while taps, text input, swipes, app launches, and other side-effecting actions do not auto-replay after a timeout. `dump_xml()` owns its own finite retry loop. When checking the thinking toggle, parse the XML already saved as `thinking-before.xml`/`thinking-after.xml`; do not immediately issue a duplicate UI dump.

Each complete run holds a non-blocking OS file lock keyed by adb serial. A second DeepSeek runner targeting the same device must fail immediately with `DeviceBusyError`; different devices remain parallel. The OS releases the lock when the process exits, including crashes. Remote XML and screenshot paths must be DeepSeek-specific and unique per client, for example `mobile-auto-deepseek-window-<pid>-<token>.xml`, never the legacy Qianwen filename.

## Runner Commands (Python Mobile Automation)

Task JSON mode:

```powershell
python -m mobile_auto_deepseek.runner --task tasks\deepseek_sample.json --dry-run
python -m mobile_auto_deepseek.runner --task tasks\deepseek_sample.json
python -m mobile_auto_deepseek.runner --task tasks\deepseek_full_test.json --serial 100.76.50.7:6666 --output results\deepseek-full-test.json --source-limit 2
```

Feishu Base mode (read questions from Feishu, write answers back):

```powershell
python -m mobile_auto_deepseek.runner `
  --base-url "https://yuoukuajing.feishu.cn/base/UiE3bhcHRaCE01sh5Anc1AZanKd?table=tblXZ8vq7SouTIuu&view=vewZsJsX7y" `
  --base-start 1 --base-end 10 --source-limit 99 --writeback `
  --lark-cli "C:\Users\Administrator\.workbuddy\bin\lark-cli.cmd" `
  --adb "C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe" `
  --serial 100.76.50.7:6666
```

Full pipeline with JS source extraction + Feishu writeback + mark-collected:

```powershell
python -m mobile_auto_deepseek.runner `
  --base-url "https://yuoukuajing.feishu.cn/base/UiE3bhcHRaCE01sh5Anc1AZanKd?table=tblXZ8vq7SouTIuu&view=vewZsJsX7y" `
  --base-start 1 --base-end 10 --source-limit 99 --writeback --mark-collected --collect-account 18870501682 --extract-sources `
  --cdp-url http://127.0.0.1:9222 `
  --lark-cli "C:\Users\Administrator\.workbuddy\bin\lark-cli.cmd" `
  --adb "C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe" `
  --serial 100.76.50.7:6666
```

**NEW in v2.0:** High-volume mode with `--link-only` (skip mobile thinking capture, fetch all content from share page API):

```powershell
python -m mobile_auto_deepseek.runner `
  --base-url "https://yuoukuajing.feishu.cn/base/UiE3bhcHRaCE01sh5Anc1AZanKd?table=tblXZ8vq7SouTIuu&view=vewZsJsX7y" `
  --base-start 1 --base-end 100 --source-limit 99 --writeback --mark-collected --collect-account 18870501682 `
  --extract-sources --link-only `
  --cdp-url http://127.0.0.1:9222 `
  --lark-cli "C:\Users\Administrator\.workbuddy\bin\lark-cli.cmd" `
  --adb "C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe" `
  --serial 100.76.50.7:6666
```

With `--link-only`, the runner skips mobile-side thinking content capture. Instead, the JS extractor (via `--extract-sources`) fetches the answer, thinking, and sources from the desktop share page API in ~3 seconds per question. This is ideal for batch collection: 30 sec answer wait + 3 sec extraction ≈ 33 sec per question, vs. 2–5 min in normal mode.

Externalized Feishu table config (switch environments by editing one JSON, not source):

```powershell
# JSON supplies the input base + answer/source writeback table IDs; CLI flags still override it.
python -m mobile_auto_deepseek.runner --feishu-config configs\feishu-deepseek-example.json --base-start 1 --base-end 10 --dry-run

python -m mobile_auto_deepseek.runner `
  --feishu-config configs\feishu-deepseek-example.json `
  --base-start 1 --base-end 100 --writeback --mark-collected `
  --extract-sources --link-only --cdp-url http://127.0.0.1:9222 `
  --lark-cli "C:\Users\Administrator\.workbuddy\bin\lark-cli.cmd" `
  --adb "C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe" `
  --serial 100.76.50.7:6666
```

- `--feishu-config` / `--writeback-config` — JSON file with `input.baseUrl` (or `baseToken`/`tableId`/`viewId`), `writeback.answerTableId`, `writeback.sourceTableId`, and `collectAccount`. Loaded at startup and applied as defaults; **CLI flags always win**. Template: `references/mobile-auto-deepseek/configs/feishu-deepseek-example.json`.
- `--answer-table-id` — Feishu table_id for the answer writeback table (defaults to the built-in DeepSeek answer table).
- `--source-table-id` — Feishu table_id for the source table (flows to the JS extractor).

Only table IDs change between Feishu environments — field names and column structure stay fixed (`feishu_base.py` `ANSWER_WRITEBACK_FIELDS` / `SOURCE_WRITEBACK_FIELDS`).

For parallel runs, pass a unique `--serial` and a unique `--output` per process.
The runner refuses to guess when multiple adb devices are online, which prevents cross-device runs.

## JS Source Extractor Commands (Standalone)

Use the JS extractor on its own when you already have a DeepSeek share URL.

```powershell
# Extract + write to Feishu
node deepseek-source-extractor\run.js `
  --url "https://chat.deepseek.com/share/<share_id>" `
  --natural-question NQ-001 `
  --base-token <feishu_app_token> --table-id <feishu_table_id>

# Extract only
node deepseek-source-extractor\run.js `
  --url "https://chat.deepseek.com/share/<share_id>" `
  --extract-only --output sources.json

# Write only from existing JSON
node deepseek-source-extractor\run.js `
  --write-only --sources sources.json `
  --natural-question NQ-001 `
  --base-token <feishu_app_token> --table-id <feishu_table_id>
```

The JS extractor needs Chrome running with `--remote-debugging-port=9222` and the target DeepSeek share page already open in that Chrome.

## Required References

- `references/README.md`: migration, environment setup, ADB checks, ADB Keyboard setup, Chrome CDP setup, task JSON contract, Feishu Base mode, output contract, troubleshooting, and the cooperation diagram between the two modules.
- `references/mobile-auto-deepseek/`: runnable Python project snapshot containing `mobile_auto_deepseek/` (the package), `deepseek-source-extractor/` (the integrated JS scripts), and `configs/feishu-deepseek-example.json` (externalized Feishu table-ID template).
- `references/deepseek-source-extractor/`: standalone JS extractor reference (top-level) for agents that only need web-side source extraction.
- `references/tasks/`: task JSON examples for the Python runner.
- `references/docs/`: design notes.

## Key Source Files

### Python package (`references/mobile-auto-deepseek/mobile_auto_deepseek/`)

- `runner.py` — CLI entry point. Parse args, build task, run sessions, write results, invoke JS extractor bridge.
- `app.py` — UI automation: ensure_app, create_new_chat, enter_thinking_mode, send_question, wait_for_answer, capture_thinking_content, extract_answer_share_link.
- `source_extractor_bridge.py` — Bridge to the JS extractor. Validates share URL, locates run.js, invokes with subprocess, retries with exponential backoff.
- `feishu_base.py` — Feishu Base read/write via lark-cli. Builds tasks from Feishu rows, writes answer rows back. Writeback table IDs are read from `writeback_context` (supplied by `--feishu-config`/CLI) and fall back to the `FEISHU_ANSWER_TABLE_ID` / `FEISHU_SOURCE_TABLE_ID` constants; column structure is fixed.
- `adb_client.py` — ADB wrapper (tap, keyevent, text broadcast, dump_xml, screenshot, ime).
- `constants.py` — DeepSeek package name (`com.deepseek.chat`), ADB Keyboard IME, UI text constants.
- `ocr.py` — Windows Media.Ocr wrapper for screenshot-based OCR fallback.
- `task_schema.py` — Task JSON loading and normalization.
- `ui_xml.py` — uiautomator XML parsing.
- `thinking_capture.py` — Thinking-detail page capture helpers.
- `source_links.py` — Legacy in-app source link probing (largely superseded by the JS extractor).
- `result_writer.py` — Result JSON writer.
- `artifacts.py` — State snapshots (XML + nodes).
- `time_utils.py` — ISO timestamps and stamps.

### JS extractor (`references/deepseek-source-extractor/` and `references/mobile-auto-deepseek/deepseek-source-extractor/`)

- `run.js` — Main entry. Parses args, calls extract-sources.js, then write-feishu.js. Supports `--extract-only`, `--write-only`, `--dry-run`.
- `extract-sources.js` — Connects to Chrome via CDP (`connectOverCDP`), finds the DeepSeek share tab by share_id, replays the share/content API from the page context, walks `data.session.record_list[].response_messages[].meta_data.sources[].content.list[]` (and the `multi_load[].content.docs[]` variant), and returns clean source objects with real URLs.
- `write-feishu.js` — Builds Feishu rows (来源标题, 来源URL, 引用来源类型, 引用来源平台, 关联自然问句) and creates records via `lark-cli base +record-batch-create`.
- `package.json` — Declares `playwright-core` dependency.

## Operating Rules

- Preserve question text exactly. Do not paraphrase.
- Prefer one fresh DeepSeek chat per question unless a task explicitly requests reuse.
- Do not automate login or captcha. Report those cases as `blocked`.
- Do not fabricate source URLs from source titles. Real source URLs come from the JS extractor (via the share/content API) or, legacy, from in-app share/copy/paste.
- Do not toggle DeepSeek thinking mode unless the normalized question value is the literal boolean `true`. In particular, do not treat missing, `null`, `false`, or the string `"true"` as authorization to tap.
- Keep every ADB subprocess bounded by the shared 15-second timeout. Retry reads only; never automatically replay a timed-out UI action that could tap or type twice.
- Hold `DeviceProcessLock` for the whole task and use per-client DeepSeek remote artifact names. Never allow two DeepSeek runners to drive the same adb serial concurrently.
- Treat `partial` as useful output: answer text may exist even when some source links or share links failed.
- Keep generated `results/`, `outputs/`, screenshots, XML dumps, and logs outside the skill unless the user explicitly asks to archive evidence.
- The JS extractor writes sources to Feishu directly. The Python runner only records a summary in the result JSON.
- The JS extractor needs Chrome with `--remote-debugging-port=9222` and the DeepSeek share page already open. The Python runner does not launch Chrome.

## ADB Keyboard Notes

Use `com.android.adbkeyboard/.AdbIME` for Chinese input.

1. Install `keyboardservice-debug.apk` on the target device (the Doubao skill ships it; the DeepSeek skill reuses the same APK).
2. Open Android input-method settings and enable `ADB Keyboard`.
3. Switch the current input method to `com.android.adbkeyboard/.AdbIME`.
4. Confirm with `adb shell ime list -s` and `adb shell settings get secure default_input_method`.

If live runs fail with `adb_keyboard_not_installed`, install the APK and set the IME again.

On some emulator ROMs, `ime enable` and `ime set` are blocked by policy. Use the Settings UI plus `adb shell dumpsys input_method` to confirm the service is active.

## Chrome CDP Notes (For JS Source Extractor)

The JS extractor replays the share/content API from the page context so it carries the correct cookies and origin. This requires:

1. Close all Chrome windows.
2. Launch Chrome with `--remote-debugging-port=9222`.
3. Open the DeepSeek share page in that Chrome.
4. Confirm `Invoke-RestMethod http://127.0.0.1:9222/json/version` returns a version payload.

The default CDP URL is `http://127.0.0.1:9222`. Override with `--cdp-url` (Python) or `--cdp` (JS).

## Fast Debug Path

1. `adb devices` — confirm the device is online.
2. `adb shell settings get secure default_input_method` — confirm `com.android.adbkeyboard/.AdbIME`.
3. `Invoke-RestMethod http://127.0.0.1:9222/json/version` — confirm Chrome CDP is running.
4. `python -m mobile_auto_deepseek.runner --task tasks\deepseek_sample.json --dry-run` — validate the task.
5. `python -m mobile_auto_deepseek.runner --task tasks\deepseek_sample.json --debug` — live run with artifacts.
6. If source extraction fails, run the JS extractor standalone with `--extract-only --output sources.json` and inspect the JSON.
7. If UI selectors fail, inspect `results/snapshots/<session>-<index>-<stamp>/*.xml` and compare resource ids in `mobile_auto_deepseek/constants.py`.
8. For parallel runs, give each process a distinct `--serial` and `--output`.
