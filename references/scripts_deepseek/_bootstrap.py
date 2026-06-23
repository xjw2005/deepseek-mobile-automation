"""DeepSeek 探测脚本公共 bootstrap。

将项目根加入 sys.path，使探测脚本能直接 import 未来的 mobile_auto_deepseek 包。
在 mobile_auto_deepseek 尚未创建前，探测脚本只依赖 mobile_auto_qianwen.adb_client
与 mobile_auto_qianwen.ui_xml，这两个模块与 App 无关，可直接复用。
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
