# DeepSeek Source Extractor

Extract reference sources from a DeepSeek share page (`https://chat.deepseek.com/share/<id>`)
and write them to a Feishu Bitable.

## Why this exists (ADR-001 U4)

DeepSeek 手机端的「来源」面板是原生 `View`，只显示 标题/站点/日期，**不暴露真实 URL**。
因此来源提取走 `cdp_bridge` 路线：用桌面 Chrome 打开手机端复制出来的分享链接，从渲染后的
分享页 DOM 抓取外链。

> NOTE: DeepSeek 未公开稳定的 share/info 内部 API（与千问 `chat2-api` 不同），本提取器
> 仅从分享页 DOM 抓取 `<a href>` 外链 + 可见文本，不依赖任何反向工程的内部接口。

## Setup

```bash
cd deepseek-source-extractor
npm install
# 启动带 CDP 的 Chrome
chrome.exe --remote-debugging-port=9222
```

## Usage

```bash
# 完整流程：提取 + 写回飞书
node run.js \
  --url "https://chat.deepseek.com/share/o7a2kswga666sdv2di" \
  --natural-question NQ-001 \
  --base-token <app_token> \
  --table-id tblOa8d90WFOV7hG

# 仅提取
node run.js --url "https://chat.deepseek.com/share/xxxx" --extract-only --output sources.json

# 仅写回（从已有 JSON）
node run.js --write-only --sources sources.json \
  --natural-question NQ-001 --base-token <app_token> --table-id tblOa8d90WFOV7hG
```

## Files

- `run.js` — combined extract + write pipeline (Python bridge invokes this).
- `extract-sources.js` — CDP connect → open/locate share page → scrape DOM anchors.
- `write-feishu.js` — build rows and create records via `lark-cli`.

## Output fields (写入飞书来源表)

`来源标题`, `来源URL`, `引用来源类型`, `引用来源平台`, `关联自然问句`
