# DeepSeek Mobile Automation Migration README

This reference explains how to move the entire DeepSeek mobile automation integration to another agent or computer and run it with minimal context loss.

The integration has **two cooperating modules**:

1. **DeepSeek来源提取 (DeepSeek Source Extractor)** — a Node.js script that extracts real reference source URLs from a DeepSeek share page by replaying the share/content API through Chrome DevTools Protocol (CDP).
2. **跑移动端 (DeepSeek Mobile Runner)** — a Python package that drives the DeepSeek Android app via ADB, captures answers / thinking content / share links, and (optionally) invokes the JS extractor to write sources back to Feishu.

The Python runner is the orchestrator. When `--extract-sources` is enabled, it captures the answer share link on the phone, hands it to the JS extractor, and the JS extractor writes the sources to Feishu.

## Changelog / 变更说明

### 2026-06-24 — 飞书表 ID 外置

- **Externalized Feishu table IDs**: new `--feishu-config` (alias `--writeback-config`) loads a JSON with `input.baseUrl`/`baseToken`/`tableId`/`viewId`, `writeback.answerTableId`, `writeback.sourceTableId`, and `collectAccount`; applied as defaults with **CLI overriding JSON**. New `--answer-table-id` flag. Template: `mobile-auto-deepseek/configs/feishu-deepseek-example.json`.
- `write_feishu_result` / `planned_writeback` now read the answer/source table IDs from `writeback_context` and fall back to the `FEISHU_ANSWER_TABLE_ID` / `FEISHU_SOURCE_TABLE_ID` constants. Field names/column structure are unchanged — switching Feishu environments usually means editing only the table IDs in the JSON, no source edits.
- (`--link-only` was already added in v2.0 and is unchanged here.)

## What This Skill Contains

```text
references/
  mobile-auto-deepseek/             # full Python project workspace (module 2)
    mobile_auto_deepseek/           # Python package
      __init__.py
      adb_client.py                 # ADB wrapper
      app.py                        # UI automation (tap, swipe, share, thinking capture)
      artifacts.py                  # state snapshots
      constants.py                  # package name (com.deepseek.chat), IME, UI text constants
      feishu_base.py                # Feishu Base read/write via lark-cli
      ocr.py                        # Windows Media.Ocr wrapper for screenshots
      result_writer.py              # result JSON writer
      runner.py                     # CLI entry point (python -m mobile_auto_deepseek.runner)
      source_extractor_bridge.py    # bridge: invokes deepseek-source-extractor/run.js
      source_links.py               # legacy in-app source link probing
      task_schema.py                # task JSON loading and normalization
      thinking_capture.py           # thinking-detail page capture
      time_utils.py                 # ISO timestamps and stamps
      ui_xml.py                     # uiautomator XML parsing
    configs/                        # externalized Feishu table-ID config
      feishu-deepseek-example.json  # --feishu-config template (only table IDs change per env)
  deepseek-source-extractor/        # JS extractor (module 1, standalone reference)
    run.js                          # main entry: extract + write to Feishu
    extract-sources.js              # CDP-based source URL extraction
    write-feishu.js                 # Feishu Bitable writeback
    package.json
    package-lock.json
    README.md
  tasks/                            # task JSON examples
    deepseek_sample.json
    deepseek_smoke.json
    deepseek_full_test.json
  scripts_deepseek/                 # probe and debug scripts
  docs/                             # design notes
```

The runnable Python project snapshot is under `references/mobile-auto-deepseek/`.
The standalone JS extractor is under `references/deepseek-source-extractor/` for agents that only need web-side source extraction.

## Restore On A New Computer

1. Create a workspace folder, for example `D:\CursorProjects\mobile-auto-deepseek`.
2. Copy everything from `references/mobile-auto-deepseek/` into that workspace. The workspace must contain:
   - `mobile_auto_deepseek/` (the Python package)
   - `deepseek-source-extractor/` (the JS scripts, sibling of the Python package)
3. Create runtime folders if they are missing:

```powershell
New-Item -ItemType Directory -Force -Path tasks, results, outputs
```

4. Copy task examples:

```powershell
Copy-Item <skill>\references\tasks\*.json .\tasks\
```

5. Install Python dependencies (the runner only needs the standard library + the JS extractor's npm modules):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

6. Install Node.js dependencies for the JS extractor:

```powershell
cd deepseek-source-extractor
npm install
cd ..
```

7. Confirm `lark-cli` is on PATH (Feishu read/write). If not, pass `--lark-cli <path-to-lark-cli.cmd>`.

## Android And ADB Setup

Install Android platform tools and locate `adb.exe`.
Common Windows path:

```text
C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe
```

Check devices:

```powershell
adb devices
```

If multiple devices are connected, pass `--serial <device-id>` to the runner.

Every ADB subprocess is limited to 15 seconds. Read-only commands retry once by default; side-effecting commands such as tap, swipe, text input, IME changes, and app start/stop do not auto-replay after timeout. UI hierarchy capture has its own finite retry loop. Thinking-toggle detection parses the XML from the first saved dump instead of issuing a second consecutive `uiautomator dump`.

The DeepSeek runner also holds a non-blocking OS file lock for the full task, keyed by adb serial. If another DeepSeek runner already controls that device, the new process exits immediately with `DeviceBusyError`; the lock is automatically released by the OS when its owner exits or crashes. Temporary UI files are unique per client and DeepSeek-specific: `/sdcard/mobile-auto-deepseek-window-<pid>-<token>.xml` and `/sdcard/mobile-auto-deepseek-screen-<pid>-<token>.png`.

## ADB Keyboard Setup

DeepSeek mobile runs need Chinese input. The runner broadcasts UTF-8 text through ADB Keyboard (`com.android.adbkeyboard/.AdbIME`).

1. Install `keyboardservice-debug.apk` (reuse the APK from the Doubao skill).
2. Open Android input-method settings and enable `ADB Keyboard`.
3. Switch the current input method to `com.android.adbkeyboard/.AdbIME`.
4. Confirm with:

```powershell
adb shell ime list -s
adb shell settings get secure default_input_method
```

If live runs fail with `adb_keyboard_not_installed`, install the APK and set the IME again.

## Chrome CDP Setup (For JS Source Extractor)

The JS extractor replays the share/content API from the page context so it carries the correct cookies and origin. This requires:

1. Close all Chrome windows.
2. Launch Chrome with `--remote-debugging-port=9222`.
3. Open the DeepSeek share page in that Chrome.
4. Confirm CDP is running:

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

The default CDP URL is `http://127.0.0.1:9222`. Override with `--cdp-url` (Python) or `--cdp` (JS).

## Task JSON Contract

A task JSON file defines one or more sessions, each with one or more questions.

Example (`tasks/deepseek_sample.json`):

```json
{
  "taskName": "deepseek-sample",
  "mode": "separate",
  "thinking": true,
  "device": {
    "adb": "C:\\Users\\Administrator\\AppData\\Local\\Android\\Sdk\\platform-tools\\adb.exe",
    "serial": "100.76.50.7:6666"
  },
  "sessions": [
    {
      "sessionName": "deepseek-q1",
      "newChat": true,
      "thinking": true,
      "questions": [
        "请用三句话解释什么是复利，并举例说明。"
      ]
    }
  ],
  "options": {
    "sourceLimit": 2,
    "waitStableSeconds": 2,
    "intervalMs": 1000,
    "timeoutMs": 180000,
    "answerShareMaxScrolls": 8,
    "debug": {
      "enabled": false,
      "screenshots": false,
      "currentFocus": false
    }
  },
  "output": "results/deepseek-sample.json"
}
```

Fields:

- `taskName` — human-readable task name.
- `mode` — `"separate"` (one chat per question) or `"reuse"` (reuse the same chat).
- `thinking` — deep-thinking request. Only the literal boolean `true` force-enables the UI toggle; missing, `null`, and `false` preserve its current state.
- `device.adb` — ADB executable path.
- `device.serial` — Android device serial.
- `sessions[].sessionName` — session identifier.
- `sessions[].newChat` — whether to start a fresh chat before this session.
- `sessions[].thinking` — session-level thinking override.
- `sessions[].questions` — list of question strings.
- `options.sourceLimit` — how many sources to collect per question.
- `options.waitStableSeconds` — how long to wait for answer stability.
- `options.debug.enabled` — keep screenshots and XML artifacts.
- `output` — result JSON path.

## Feishu Base Mode

Instead of a task JSON, the runner can read selected rows from a Feishu Base.

Required fields in the Feishu table:

- `问题` — question text sent to DeepSeek.
- `关联自然问句` — written back with the answer/source rows.
- `是否开启深度思考` — per-row thinking request. `是` force-enables it; other values leave the current App switch untouched.
- `是否本次采集` — only rows set to `是` are selected.

### Standard Mode (mobile capture + JS extractor)

```powershell
python -m mobile_auto_deepseek.runner `
  --base-url "https://yuoukuajing.feishu.cn/base/UiE3bhcHRaCE01sh5Anc1AZanKd?table=tblXZ8vq7SouTIuu&view=vewZsJsX7y" `
  --base-start 1 --base-end 10 `
  --writeback --mark-collected --collect-account 18870501682 `
  --lark-cli lark-cli.cmd `
  --adb "C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe" `
  --serial 100.76.50.7:6666 `
  --extract-sources --cdp-url http://127.0.0.1:9222
```

### Link-Only Mode (--link-only + --extract-sources)

**Recommended for production.** Skips mobile-side thinking/answer capture entirely; all content (answer, thinking, sources) comes from the JS extractor's share/content API replay.

```powershell
python -m mobile_auto_deepseek.runner `
  --base-url "https://yuoukuajing.feishu.cn/base/UiE3bhcHRaCE01sh5Anc1AZanKd?table=tblXZ8vq7SouTIuu&view=vewZsJsX7y" `
  --base-start 10 --base-end 10 `
  --serial 100.76.50.7:6666 `
  --adb "C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe" `
  --writeback --extract-sources --cdp-url http://127.0.0.1:9222 `
  --lark-cli lark-cli.cmd --link-only
```

**Why link-only is better:**

| Aspect | Standard Mode | Link-Only Mode |
|--------|--------------|----------------|
| Answer source | Mobile OCR (viewport-limited) | **share/content API (complete)** |
| Thinking content | Mobile scroll+OCR (fragile) | **THINK fragments from API (clean)** |
| Sources | N/A | **JS extractor (real URLs)** |
| Speed | Slower (scrolling, OCR) | **Faster (no capture overhead)** |
| Reliability | Depends on UI stability | **Depends on CDP Chrome** |

**Important:** `--link-only` **must** be paired with `--extract-sources`. Without it, mobile capture is skipped and no API fallback exists — you get empty results. The runner validates this at startup and errors early if violated.

`--base-start` and `--base-end` are 1-based and inclusive. The runner reads that row range first, then only keeps rows whose `是否本次采集` value is `是`.

If `lark-cli` is not on `PATH`, pass `--lark-cli <path-to-lark-cli.cmd>`.

## Output Contract

The runner writes a JSON result to the task's `output` path.

Structure:

```json
{
  "taskName": "deepseek-sample",
  "mode": "separate",
  "startedAt": "2026-06-22T10:00:00Z",
  "finishedAt": "2026-06-22T10:05:00Z",
  "sessions": [
    {
      "sessionName": "deepseek-q1",
      "newChat": true,
      "thinking": true,
      "results": [
        {
          "index": 1,
          "question": "请用三句话解释什么是复利，并举例说明。",
          "askedAt": "2026-06-22T10:00:00Z",
          "finishedAt": "2026-06-22T10:05:00Z",
          "answer": "复利是指...",
          "thinkingContent": "深度思考内容...",
          "sources": [
            {
              "index": 1,
              "title": "来源标题",
              "url": "https://example.com/article",
              "platform": "知乎",
              "method": "js_extractor",
              "status": "success"
            }
          ],
          "answerShareUrl": "https://chat.deepseek.com/share/<id>",
          "status": "success",
          "error": null,
          "debug": { ... }
        }
      ]
    }
  ]
}
```

Fields:

- `status` — `"success"` (all ok), `"partial"` (answer ok but some sources/share failed), `"blocked"` (login/captcha), `"failed"` (no answer).
- `answer` — captured answer text.
- `thinkingContent` — captured deep-thinking content (if enabled).
- `sources` — extracted source objects (from JS extractor).
- `answerShareUrl` — DeepSeek share link.
- `debug` — internal debug info (screenshots, XML, timing).

## JS Source Extractor Details

The JS extractor (`deepseek-source-extractor/run.js`) supports three modes:

1. **Extract + write** (default, full pipeline):

```powershell
node run.js --url "https://chat.deepseek.com/share/<id>" --natural-question NQ-001 --base-token <token> --table-id <table-id>
```

2. **Extract only** (no Feishu writeback):

```powershell
node run.js --url "https://chat.deepseek.com/share/<id>" --extract-only --output sources.json
```

3. **Write only** (from existing JSON):

```powershell
node run.js --write-only --sources sources.json --natural-question NQ-001 --base-token <token> --table-id <table-id>
```

The extractor needs Chrome running with `--remote-debugging-port=9222` and the target DeepSeek share page already open.

### Extract-Only Mode: How It Works

When `base_token` is empty, the bridge ([`source_extractor_bridge.py`](mobile_auto_deepseek/source_extractor_bridge.py)) automatically switches to **extract-only mode**. The key rule is simple:

> **`extract_only = not base_token`** — base_token presence is the **sole** signal that distinguishes full pipeline from extract-only.

A `table_id` alone cannot drive a writeback (the lark-cli call needs an app token), so having a table_id without a base_token still runs in extract-only mode. This was a bug fix: previously the check required both `base_token` AND `table_id` to be empty, but the runner always fills in a default `table_id`, which caused false "full pipeline" detection and the error `base_token is required for Feishu source table writeback`.

### Thinking Content Extraction from API

In link-only mode (or when JS extractor succeeds), the runner replaces both `answer` and `thinkingContent` with data from the share/content API — this is more complete than mobile OCR capture.

**Thinking content extraction logic** ([`extract-sources.js`](deepseek-source-extractor/extract-sources.js)):

1. The API returns `message.fragments[]`, each with a `type` field.
2. All fragments where `type === "THINK"` are **concatenated in order**.
3. Fragments of type `"SEARCH"` or `"WEB_READ"` are **excluded** — these are search queries and web page reading records, not reasoning.
4. The result is clean thinking/reasoning text without noise.

Example from a real run (3 THINK fragments → 260 chars):

```
[THINK fragment 1] 用户询问的是关于"容易吐奶的宝宝适合哪些温和奶粉"的问题...
[THINK fragment 2] 需要考虑几个关键因素：1) 吐奶原因...
[THINK fragment 3] 基于以上分析，推荐以下几款温和奶粉...
```

### What the Runner Does After JS Extraction

When the JS extractor succeeds, the runner performs an **API answer override**:

```python
# From share/content API (authoritative, complete)
api_answer = extracted.get("answer")        # e.g., 1578 chars
api_thinking = extracted.get("thinkingContent")  # e.g., 260 chars

# Replace mobile-captured (possibly truncated) values
if api_answer:
    answer = api_answer          # replaces mobile OCR answer (~545 chars)
if api_thinking:
    expert_answer["thinking"] = api_thinking  # replaces mobile scroll+OCR
```

This means even if you use standard mode (without `--link-only`), a successful JS extraction will upgrade your results to the complete API versions.

## Troubleshooting

### `base_token is required for Feishu source table writeback`

This means the JS extractor was invoked in **full pipeline mode** (with a `table_id`) but no `base_token` was provided. The bridge checks:

```python
extract_only = not base_token   # only base_token matters
```

**Fix options:**
- Add `--base-token <token>` or use `--base-url` (which extracts the token from the URL)
- Or run without `--writeback` to stay in extract-only mode
- For task JSON runs: if you only want content (not Feishu writeback), omit `--base-token` — extract-only will activate automatically

### `--link-only requires --extract-sources`

The runner validates this at startup in [`validate_args()`](mobile_auto_deepseek/runner.py). Without `--extract-sources`, `--link-only` skips mobile capture but has no API fallback → empty results. Always pair them.

### JS Extractor Failed But Mobile Capture Succeeded (partial status)

This is expected behavior when using standard mode (no `--link-only`). The runner falls back to mobile-captured answer/thinking. Status will be `"partial"` — answer is present but sources are missing. Use `--link-only --extract-sources` for end-to-end API-based results.

### ADB Keyboard Not Installed

Install `keyboardservice-debug.apk` and set the IME:

```powershell
adb install keyboardservice-debug.apk
adb shell ime enable com.android.adbkeyboard/.AdbIME
adb shell ime set com.android.adbkeyboard/.AdbIME
```

### Multiple Devices Connected

Pass `--serial` explicitly:

```powershell
python -m mobile_auto_deepseek.runner --task tasks\deepseek_sample.json --serial emulator-5556
```

### Chrome CDP Not Running

Launch Chrome with CDP:

```powershell
chrome.exe --remote-debugging-port=9222
```

### Feishu Writeback Failed

Check `lark-cli` path and permissions:

```powershell
lark-cli --version
lark-cli base +record-batch-create --help
```

### UI Selectors Failed

Inspect the captured XML in `results/snapshots/<session>-<index>-<stamp>/*.xml` and compare resource ids in `mobile_auto_deepseek/constants.py`.

## DeepSeek-Specific Notes

- Target app: `com.deepseek.chat`.
- Thinking toggle: `深度思考` (text only, no `resource-id`).
- Thinking state is read from the toggle's clickable parent: `checkable="true" checked="true"` means enabled. The runner taps only for an explicit boolean `thinking: true`, skips an already-enabled toggle, and verifies `checked="true"` after tapping. Missing, `null`, and `false` never toggle it.
- Answer share flow: `分享` → `创建链接` → `创建并复制` produces `https://chat.deepseek.com/share/<id>`.
- Share pages need no login (`任何获得链接的人都可以查看你分享的对话`).
- The JS extractor uses `/api/v0/share/content?share_id=...` API.

## Cooperation Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│                     Feishu Base (optional)                   │
│  问题, 关联自然问句, 是否开启深度思考, 是否本次采集          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              Python Runner (mobile_auto_deepseek)            │
│  - Reads Feishu rows or task JSON                            │
│  - Drives DeepSeek Android app via ADB                       │
│  - Captures answer, thinking, share link                     │
│  - Invokes JS extractor (--extract-sources)                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│           JS Extractor (deepseek-source-extractor)           │
│  - Connects to Chrome via CDP                                │
│  - Replays share/content API from page context               │
│  - Extracts real source URLs                                 │
│  - Writes sources to Feishu Bitable                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Feishu Bitable                           │
│  AI回答采集 (answer table): 采集账号, 自然问句, AI回答, ...  │
│  引用源明细 (source table): 来源标题, 来源URL, ...           │
└─────────────────────────────────────────────────────────────┘
```

The Python runner is the orchestrator. It reads questions from Feishu or task JSON, drives the DeepSeek app, captures the share link, and (optionally) invokes the JS extractor. The JS extractor writes sources to Feishu directly.
