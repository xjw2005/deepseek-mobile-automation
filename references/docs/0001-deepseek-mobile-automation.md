# ADR-001: DeepSeek 移动端自动化实现

- **状态**: Accepted
- **日期**: 2026-06-20
- **决策者**: 工程负责人
- **实现方**: 强大 AI（直接交付）
- **基线版本**: 以 `mobile_auto_qianwen/` 当前 HEAD 为模板
- ** superseded by**: 无

---

## 1. Context（背景与目标）

### 1.1 背景

本仓库已有两套移动端自动化实现：

- **豆包（Legacy Flow）**：`mobile_auto_doubao/`，入口为顶层 `runner.py`，目标 App `com.larus.nova`。已停止迭代。
- **千问（Active Flow）**：`mobile_auto_qianwen/`，入口为 `python -m mobile_auto_qianwen.runner`，目标 App `com.aliyun.tongyi`。是当前推荐基线。

两套实现共享相同的飞书 Base 字段约定（`问题文本` / `问题ID` / `是否开启深度思考` / `是否本次采集` / `AI回答采集` / `引用源明细`），与桌面端 DeepSeek CDP runner 对齐。

### 1.2 目标

为 DeepSeek Android App 新增一套移动端自动化实现 `mobile_auto_deepseek/`，达到与千问 Active Flow 同等的可交付水平：

1. 通过 Python + ADB 控制 DeepSeek Android App 完成问答采集
2. 支持深度思考模式（若 App 提供）
3. 支持来源 URL 提取（至少一条可用路径）
4. 支持回答分享链接捕获
5. 支持飞书 Base 读写回写
6. 提供可运行的 smoke 测试与 task 样例

### 1.3 非目标

- 不做 iOS 自动化
- 不做 DeepSeek 桌面 Web 版（已有 CDP runner）
- 不重构豆包 Legacy Flow
- 不引入 AutoJS / `uiautomator2`
- 不修改飞书 Base 字段名约定

---

## 2. Decision Drivers（决策驱动因素）

| 驱动因素 | 影响 |
|---------|------|
| DeepSeek App 的 UI 结构是否暴露 resource_id | 决定定位策略是 id 优先还是文本兜底 |
| DeepSeek 是否提供"深度思考"开关及入口形态 | 决定 thinking_capture 模块的实现路径 |
| DeepSeek App 内来源列表是否暴露真实 URL | 决定走 share-copy（豆包式）还是 CDP bridge（千问式） |
| DeepSeek 分享页是否为 H5 且可被 CDP 访问 | 决定是否新建 `deepseek-source-extractor/` |
| DeepSeek 分享链接形态 | 决定 bridge 的 URL 校验正则 |
| 与千问 runner 的对齐度 | 决定复用边界 |

---

## 3. Decisions（已决策项）

> 每条决策均已收敛，实现方按表执行，不再讨论。

| # | 决策点 | 豆包做法 | 千问做法 | **DeepSeek 决策** | 理由 |
|---|--------|---------|---------|------------------|------|
| D1 | 代码骨架模板 | — | — | **抄千问** `mobile_auto_qianwen/` 整套 | Active Flow，runner/feishu_base/task_schema/result_writer 已是最新版 |
| D2 | 入口形式 | 顶层 `runner.py` | `python -m mobile_auto_qianwen.runner` | **模块入口** `python -m mobile_auto_deepseek.runner` | 与千问一致，避免顶层 runner 冲突 |
| D3 | UI 定位策略 | resource_id | 文本兜底（id 为空） | **resource_id 优先 + 文本兜底** | 先探测；千问的文本兜底代码可直接复用 |
| D4 | 思考模式入口 | "专家/深度思考" | "思考"按钮+"查看全部" | **探测后定**（见 U1） | DeepSeek 有"深度思考"开关，UI 路径未确认 |
| D5 | 来源提取路线 | Python share-copy | Node.js CDP bridge | **优先 CDP bridge，降级 share-copy** | DeepSeek 分享页若为 H5，CDP 最稳；先探测分享链形态 |
| D6 | 是否引入 OCR | 无 | 有（thinking 兜底） | **复用千问 `ocr.py`** | DeepSeek 思考内容若不可选中文本，需 OCR |
| D7 | 分享链接校验正则 | — | `qianwen.com/share/chat/` | **新增 DeepSeek 分享链接正则**（见 U2） | bridge 的 `validate_params` 依赖此正则 |
| D8 | 包名/常量 | `com.larus.nova` | `com.aliyun.tongyi` | **探测 DeepSeek 包名**（见 U3） | 写入 `constants.py` |
| D9 | 多设备/dry-run/writeback | 有 | 有 | **直接复用千问实现** | 无差异 |
| D10 | JS extractor | — | `qianwen-source-extractor/` | **新建 `deepseek-source-extractor/`**，结构对齐 | 分享页 DOM 不同，选择器必须重写 |
| D11 | 输入法 | ADB Keyboard | ADB Keyboard | **ADB Keyboard**（`com.android.adbkeyboard/.AdbIME`） | 中文输入必需，已验证 |
| D12 | 滚动策略 | swipe + keyevent 兜底 | swipe + keyevent 兜底 | **复用千问兜底逻辑** | 部分 ROM 阻止 `input swipe` |
| D13 | 日志策略 | 顶层日志 | `output_path.log` + 控制台 | **复用千问 `_setup_run_logger`** | 已含文件 + 控制台双输出 |
| D14 | 调试产物 | screenshots + xml | snapshots 目录 | **复用千问 artifacts.py** | 增量写、按题分目录 |

---

## 4. Unknowns & Probes（未知项 + 探测脚本）

> **强制流程**：实现方必须先跑完 U1–U6 探测，把结果填入第 5 节"决策回填模板"，再开始写业务代码。未知项不得用占位符进入 `constants.py`。

### U1 思考模式 UI 路径

- **探测脚本**: `scripts_deepseek/probe_thinking_entry.py --serial <serial>`
- **动作**: 启动 App → dump 首页 XML → 搜索文本"深度思考/思考/联网搜索/推理"
- **判定准则**:
  - 若找到可点击开关节点 → 记录其 `resource_id` / `text` / `bounds`，写入 `THINK_BUTTON_TEXT` 与（若有）`THINK_BUTTON_ID`
  - 若无开关 → 标记 `thinking_supported = false`，runner 中 `set_thinking_mode` 直接返回 `{"changed": false, "reason": "not_supported"}`
- **回填字段**: `THINK_BUTTON_TEXT`, `THINK_BUTTON_ID`, `VIEW_ALL_TEXT`, `thinking_supported`

### U2 分享链接形态

- **探测脚本**: `scripts_deepseek/probe_share_link.py --serial <serial>`
- **动作**: 手动触发一次分享 → 复制链接 → 通过 paste-input 读取 URL
- **判定准则**:
  - 若 URL 形如 `https://chat.deepseek.com/share/...` → 写正则 `^https?://(chat\.)?deepseek\.com/share/[A-Za-z0-9]+`
  - 若 App 内无分享入口 → 标记 `share_link_supported = false`，runner 跳过分享链接采集
- **回填字段**: `DEEPSEEK_SHARE_URL_RE`, `share_link_supported`

### U3 包名

- **探测脚本**: `scripts_deepseek/probe_package.py`
- **动作**: `adb shell pm list packages | grep -i deepseek`
- **判定准则**: 取唯一命中写入 `DEEPSEEK_PACKAGE`；若多个命中则报错让人工确认
- **回填字段**: `DEEPSEEK_PACKAGE`

### U4 来源是否在 App 内可见

- **探测脚本**: `scripts_deepseek/probe_in_app_sources.py --serial <serial>`
- **动作**: 提问一个会触发来源的问题 → dump 回答页 XML → 搜 `http`
- **判定准则**:
  - 若有 URL → 走 share-copy 路线（抄豆包 `source_links.py`）
  - 若无 URL → 走 CDP bridge 路线（抄千问 `source_extractor_bridge.py`）
- **回填字段**: `source_extraction_route` ∈ {`share_copy`, `cdp_bridge`}

### U5 思考内容是否可选中文本

- **探测脚本**: `scripts_deepseek/probe_thinking_selectable.py --serial <serial>`
- **动作**: 触发思考 → 长按思考文本 → 检查是否出现选择手柄 / `selection` 事件
- **判定准则**:
  - 可选 → 复用千问 `capture_thinking_content` 路线
  - 不可选 → 启用 OCR 路线（复用千问 `ocr.py`）
- **回填字段**: `thinking_capture_method` ∈ {`text_select`, `ocr`}

### U6 分享页是否需要登录

- **探测脚本**: `scripts_deepseek/probe_share_page_auth.py --url <share_url>`
- **动作**: CDP 打开分享页 → 检查是否跳登录页
- **判定准则**:
  - 不需要 → 直接抄千问 `run.js` 流程
  - 需要 → bridge 必须支持 cookie 注入（在 ADR 第 7 节"后续工作"中追踪）
- **回填字段**: `share_page_requires_auth` ∈ {`true`, `false`}

---

## 5. 决策回填模板

> 实现方跑完 U1–U6 后，把结果填入下表，并据此生成 `mobile_auto_deepseek/constants.py`。

> **已回填**（探测日期 2026-06-20，设备 `100.76.50.7:6666` 华为真机）。探测产物存档于 `outputs/deepseek/u1..u6/`。

```python
# mobile_auto_deepseek/constants.py —— 由 ADR-001 第 5 节回填

# U3 回填
DEEPSEEK_PACKAGE = "com.deepseek.chat"

# U1 回填
THINK_BUTTON_TEXT = "深度思考"
THINK_BUTTON_ID = ""          # 无 resource_id，走文本兜底
VIEW_ALL_TEXT = "查看全部"     # 未在思考详情页实测，沿用千问默认
thinking_supported = True

# U2 回填
DEEPSEEK_SHARE_URL_RE_PATTERN = r"^https?://(chat\.)?deepseek\.com/share/[A-Za-z0-9]+"
share_link_supported = True

# U4 回填（来源面板为原生 View，仅显示标题/站点，不暴露真实 URL → 走 CDP）
source_extraction_route = "cdp_bridge"

# U5 回填（思考详情页未实测，按 ADR 失败处理规则保守默认 OCR）
thinking_capture_method = "ocr"

# U6 回填（分享创建弹窗明示"任何获得链接的人都可以查看"，无登录页）
share_page_requires_auth = False

# 通用常量（直接复用）
DEFAULT_ADB = r"C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe"
DEFAULT_SERIAL: str | None = None
ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
INPUT_PLACEHOLDER_TEXTS = ("给 DeepSeek 发送消息", "发消息", "有问题，尽管问")
LOGIN_KEYWORDS = ("账号登录", "手机号", "验证码", "登录", "注册")
PRIVACY_KEYWORDS = ("用户协议", "隐私政策", "同意")
SHARE_BUTTON_TEXT = "分享"
CREATE_LINK_TEXT = "创建链接"
CREATE_AND_COPY_TEXT = "创建并复制"
COPY_LINK_TEXT = "复制链接"
BACK_BUTTON_DESC = "返回"
```

> **探测要点记录**：
> - U2 实测分享流程为：底部「分享」→「创建链接」→「创建并复制」→ 系统分享面板顶部显示 `https://chat.deepseek.com/share/<id>` 并已写入剪贴板。
> - U4 点击「N 个网页」展开来源面板，面板为原生 View，仅含标题/站点/日期，**无 http URL**，故来源提取必须走分享页 CDP（依赖 U2 分享链）。
> - U5 探测中 App 被 back 键退回桌面，未在思考页实测；按第 5 节"探测失败处理"规则默认 `ocr`。

---

## 6. Reuse Boundary（复用边界表，逐文件点名）

| 文件 | 处理方式 | 说明 |
|------|---------|------|
| `adb_client.py` | **直接复制**千问版本 | 无 App 特异性 |
| `ui_xml.py` | **直接复制** | 通用 XML 解析 |
| `time_utils.py` | **直接复制** | 通用时间工具 |
| `artifacts.py` | **直接复制** | 通用产物保存 |
| `task_schema.py` | **直接复制** | task JSON schema 一致 |
| `result_writer.py` | **直接复制** | 增量写逻辑一致 |
| `feishu_base.py` | **直接复制** | 飞书字段已对齐 |
| `ocr.py` | **直接复制** | U5 需要 OCR 时启用 |
| `constants.py` | **重写** | 见第 5 节回填模板 |
| `app.py` | **改写** | 定位选择器、思考模式入口、分享按钮路径按 U1/U2 结果调整 |
| `thinking_capture.py` | **改写** | 标题文本、生成中关键词、查看全部入口按 U1/U5 调整 |
| `source_links.py`（豆包式 share-copy） | **按 U4 结果决定是否引入** | 若 `source_extraction_route == share_copy` 则从豆包版本移植 |
| `source_extractor_bridge.py` | **改写** | 分享链接正则、脚本路径默认值改为 DeepSeek |
| `deepseek-source-extractor/run.js` | **新建** | DOM 选择器重写，CDP 流程抄千问 |
| `deepseek-source-extractor/extract-sources.js` | **新建** | 选择器重写 |
| `deepseek-source-extractor/write-feishu.js` | **新建** | 字段映射与千问一致 |
| `runner.py` | **改写** | import 路径、模块名、默认 `platform="DeepSeek"` |

---

## 7. Acceptance Criteria（验收清单）

> 实现完成后逐项自检，全部勾选方可交付。

- [ ] `python -m mobile_auto_deepseek.runner --task tasks/deepseek_sample.json --dry-run` 正常预览
- [ ] 真机/模拟器单题跑通：回答采集成功，`result.debug.timing` 有值
- [ ] 思考模式（若 `thinking_supported == true`）能捕获思考内容
- [ ] 来源提取：至少一种路线（share-copy 或 CDP）能拿到真实 URL
- [ ] 分享链接能捕获且通过 DeepSeek 正则校验
- [ ] 飞书 writeback：`--writeback --mark-collected` 跑通，`AI回答采集` / `引用源明细` 两表有数据
- [ ] 多设备场景下 `--serial` 必填且不串台
- [ ] `tests_smoke.py` 中对应的 deepseek smoke 用例通过
- [ ] `constants.py` 中所有常量来自 U1–U6 探测结果，无占位符
- [ ] `docs/adr/0001-deepseek-mobile-automation.md` 第 5 节"决策回填模板"已实际填值
- [ ] `README.md` 新增 DeepSeek runner 使用说明章节
- [ ] `CLAUDE.md` 架构图新增 DeepSeek Flow

---

## 8. Out of Scope（明确不做的事）

- 不做 iOS 自动化
- 不做 DeepSeek 桌面 Web 版（已有 CDP runner）
- 不重构豆包 Legacy Flow
- 不引入 AutoJS / `uiautomator2` / Appium
- 不修改飞书 Base 字段名约定
- 不做并发多设备调度（单进程单设备，靠 `--serial` 区分）
- 不做 DeepSeek 账号自动登录（首次需人工登录）

---

## 9. 后续工作（Future Work）

- 若 U6 探测出分享页需要登录：在 `deepseek-source-extractor/` 中支持 cookie 注入
- 若 DeepSeek App 后续暴露 WebView DevTools socket：评估直接 CDP 抓取，替代 share-copy
- 若来源提取稳定性不足：评估引入 `uiautomator2` 作为兜底层

---

## 10. References（参考）

- [mobile-runner-skill-design.md](file:///d:/CursorProjects/mobile-auto-doubao/docs/mobile-runner-skill-design.md)
- [CLAUDE.md](file:///d:/CursorProjects/mobile-auto-doubao/CLAUDE.md)
- [千问 runner.py](file:///d:/CursorProjects/mobile-auto-doubao/mobile_auto_qianwen/runner.py)
- [千问 app.py](file:///d:/CursorProjects/mobile-auto-doubao/mobile_auto_qianwen/app.py)
- [千问 source_extractor_bridge.py](file:///d:/CursorProjects/mobile-auto-doubao/mobile_auto_qianwen/source_extractor_bridge.py)
- [豆包 source_links.py](file:///d:/CursorProjects/mobile-auto-doubao/mobile_auto_doubao/source_links.py)
- [豆包 answer_share.py](file:///d:/CursorProjects/mobile-auto-doubao/mobile_auto_doubao/answer_share.py)
- [千问 run.js](file:///d:/CursorProjects/mobile-auto-doubao/qianwen-source-extractor/run.js)
