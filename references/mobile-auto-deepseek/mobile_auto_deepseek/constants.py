# mobile_auto_deepseek/constants.py
# 由 ADR-001 (docs/adr/0001-deepseek-mobile-automation.md) 第 5 节"决策回填模板"回填生成。
# 探测日期 2026-06-20，设备 100.76.50.7:6666（华为真机），探测产物存档于 outputs/deepseek/u1..u6/。

# —— U3: 包名 ——
DEEPSEEK_PACKAGE = "com.deepseek.chat"

# —— U1: 思考模式入口（无 resource_id，走文本兜底） ——
THINK_BUTTON_TEXT = "深度思考"
THINK_BUTTON_ID = ""          # 探测结果为空：DeepSeek 首页"深度思考"开关无 resource-id
VIEW_ALL_TEXT = "查看全部"     # 未在思考详情页实测，沿用千问默认
thinking_supported = True

# —— U2: 分享链接 ——
# 实测链接：https://chat.deepseek.com/share/o7a2kswga666sdv2di
DEEPSEEK_SHARE_URL_RE_PATTERN = r"^https?://(chat\.)?deepseek\.com/share/[A-Za-z0-9]+"
share_link_supported = True

# —— U4: 来源提取路线 ——
# 来源面板为原生 View，仅显示标题/站点/日期，不暴露真实 URL → 走分享页 CDP bridge。
source_extraction_route = "cdp_bridge"

# —— U5: 思考内容捕获方式（未在思考详情页实测，按 ADR 失败处理规则保守默认 OCR） ——
thinking_capture_method = "ocr"

# —— U6: 分享页是否需要登录 ——
# 分享创建弹窗明示"任何获得链接的人都可以查看你分享的对话" → 无需登录。
share_page_requires_auth = False

# —— 通用常量 ——
DEFAULT_ADB = r"C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe"
DEFAULT_SERIAL: str | None = None

ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"

# DeepSeek 输入框无稳定 resource-id，留空走 EditText / placeholder 兜底
INPUT_ID = ""
INPUT_PLACEHOLDER_TEXTS = ("给 DeepSeek 发送消息", "发消息", "有问题，尽管问")

# —— 分享流程文案（U2 实测）：底部「分享」→「创建链接」→「创建并复制」→ 系统分享面板显示 URL ——
SHARE_BUTTON_TEXT = "分享"
CREATE_LINK_TEXT = "创建链接"
CREATE_AND_COPY_TEXT = "创建并复制"
COPY_LINK_TEXT = "复制链接"
BACK_BUTTON_DESC = "返回"

LOGIN_KEYWORDS = ("账号登录", "手机号", "验证码", "登录", "注册")
PRIVACY_KEYWORDS = ("用户协议", "隐私政策", "同意")

# 平台标识（写入飞书 / 结果 JSON）
DEEPSEEK_PLATFORM = "DeepSeek"
