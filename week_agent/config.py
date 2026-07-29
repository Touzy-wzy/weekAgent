"""全局配置与路径常量"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（week_agent 的上一级）
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# 加载 .env
load_dotenv(PROJECT_ROOT / ".env")

# FlowUs MCP 服务器地址
FLOWUS_MCP_URL = os.getenv("FLOWUS_MCP_URL", "https://mcp.flowus.cn/message")

# OAuth 回调端口
OAUTH_CALLBACK_PORT = 18923
OAUTH_REDIRECT_URI = f"http://localhost:{OAUTH_CALLBACK_PORT}/callback"

# Token 持久化文件（保持根目录，兼容旧版）
TOKEN_FILE = PROJECT_ROOT / ".flowus_token.json"

# 内容输出目录（原 weekAgent/）
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 静态资源目录
STATIC_DIR = PROJECT_ROOT / "static"

# 默认项目名
DEFAULT_PROJECT = os.getenv("FLOWUS_DEFAULT_PROJECT", "积成电子")

# 项目根页面 ID 映射（FlowUs 文件夹的 page_id）
# 当语义搜索找不到项目根时，从此映射直接取 ID
# 格式: "项目名": "page_id"
# 可在 .env 中设置 FLOWUS_PROJECT_ROOT_ID_<项目名> 覆盖
FLOWUS_PROJECT_ROOT_IDS: dict[str, str] = {
    "积成电子": os.getenv("FLOWUS_PROJECT_ROOT_ID_JCED", "2312dc25-8329-4e99-8c9c-0e277481533e"),
}
