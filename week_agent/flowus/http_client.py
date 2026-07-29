"""FlowUs HTTP/JSON-RPC 客户端 - 使用存储的 OAuth token 直连

专为 Web 服务和 Agent 工具场景设计，不依赖浏览器回调。
"""

import json
from typing import Any

import httpx

from week_agent.config import FLOWUS_MCP_URL, TOKEN_FILE


def _load_token() -> str | None:
    """从文件加载 access token"""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return data.get("tokens", {}).get("access_token")
    except Exception:
        return None


class FlowUsHTTPClient:
    """基于直接 HTTP/JSON-RPC 的 FlowUs MCP 客户端"""

    SERVER = FLOWUS_MCP_URL

    def __init__(self):
        self._token = _load_token()
        if not self._token:
            raise RuntimeError(
                "未找到 FlowUs token。请先运行 `python run.py --cli` 完成 OAuth 授权。"
            )

    def _headers(self, session_id: str | None = None) -> dict:
        h = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            h["mcp-session-id"] = session_id
        return h

    async def with_session(self, callback):
        """打开一个持久 MCP 会话，执行回调函数。

        回调签名: async def callback(client: httpx.AsyncClient, session_id: str) -> Any
        """
        async with httpx.AsyncClient(timeout=60) as http:
            # 1. Initialize
            r = await http.post(
                self.SERVER,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "week-agent", "version": "1.0"},
                    },
                },
                headers=self._headers(),
            )
            if r.status_code != 200:
                raise RuntimeError(
                    f"MCP initialize failed: {r.status_code} {r.text[:200]}"
                )

            session_id = r.headers.get("mcp-session-id", "")
            if not session_id:
                raise RuntimeError("No session ID in initialize response")

            return await callback(http, session_id)

    async def call_tool(
        self,
        http: httpx.AsyncClient,
        session_id: str,
        tool_name: str,
        arguments: dict | None = None,
        req_id: int = 2,
    ) -> Any:
        """在会话中调用 MCP 工具"""
        r = await http.post(
            self.SERVER,
            json={
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}},
            },
            headers=self._headers(session_id),
        )
        if r.status_code != 200:
            raise RuntimeError(f"Tool call failed: {r.status_code} {r.text[:200]}")
        return r.json()


# 全局单例
_client: FlowUsHTTPClient | None = None


def get_http_client() -> FlowUsHTTPClient:
    global _client
    if _client is None:
        _client = FlowUsHTTPClient()
    return _client
