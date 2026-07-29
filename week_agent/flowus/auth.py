"""FlowUs OAuth 认证 - Token 持久化存储"""

import json
from typing import Any

from mcp.client.auth.oauth2 import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthClientProvider,
    OAuthToken,
    TokenStorage,
)

from week_agent.config import OAUTH_CALLBACK_PORT, OAUTH_REDIRECT_URI, TOKEN_FILE


class FileTokenStorage(TokenStorage):
    """基于文件的 Token 存储，避免每次都需要重新授权"""

    def __init__(self, filepath=None):
        self.filepath = TOKEN_FILE if filepath is None else filepath
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None
        self._load()

    def _load(self) -> None:
        if not self.filepath.exists():
            return
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            if "tokens" in data and data["tokens"]:
                self._tokens = OAuthToken(**data["tokens"])
            if "client_info" in data and data["client_info"]:
                self._client_info = OAuthClientInformationFull(**data["client_info"])
        except Exception:
            pass

    def _save(self) -> None:
        data: dict[str, Any] = {}
        if self._tokens:
            data["tokens"] = self._tokens.model_dump(mode="json")
        if self._client_info:
            data["client_info"] = self._client_info.model_dump(mode="json")
        self.filepath.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens
        self._save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info
        self._save()


def build_oauth_provider(server_url: str) -> OAuthClientProvider:
    """构建 OAuth 认证提供者（含本地回调服务器）

    注意：此函数内部使用了 asyncio.Event / asyncio.start_server，必须在事件循环内调用。
    """
    import asyncio
    import webbrowser
    from urllib.parse import parse_qs, urlparse

    client_metadata = OAuthClientMetadata(
        redirect_uris=[OAUTH_REDIRECT_URI],
        client_name="FlowUs-MCP-Client",
    )

    callback_event: asyncio.Event = asyncio.Event()
    callback_result: dict[str, str | None] = {"code": None, "state": None}

    async def redirect_handler(url: str) -> None:
        print("\n正在打开浏览器进行 OAuth 授权...")
        print(f"授权地址: {url}\n")
        webbrowser.open(url)

    async def callback_handler() -> tuple[str, str | None]:
        async def _handle_callback(reader, writer):
            request_line = await asyncio.wait_for(reader.readline(), timeout=120)
            request_line = request_line.decode()

            if "GET /callback" in request_line:
                parsed = urlparse(request_line.split()[1])
                params = parse_qs(parsed.query)
                callback_result["code"] = params.get("code", [None])[0]
                callback_result["state"] = params.get("state", [None])[0]

            if callback_result["code"]:
                body = "<html><body><h2>授权成功!</h2><p>您可以关闭此页面，回到程序中即可继续。</p></body></html>"
            else:
                body = "<html><body><h2>授权失败</h2><p>未收到授权码，请重试。</p></body></html>"

            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body.encode())}\r\n"
                "Connection: close\r\n"
                "\r\n"
                f"{body}"
            )
            writer.write(response.encode())
            await writer.drain()
            writer.close()
            callback_event.set()

        # 尝试绑定端口
        for port in [OAUTH_CALLBACK_PORT, 18924, 18925, 0]:
            try:
                server = await asyncio.start_server(_handle_callback, "127.0.0.1", port)
                if port == 0:
                    sock = server.sockets[0]
                    port = sock.getsockname()[1]
                break
            except OSError:
                continue
        else:
            raise RuntimeError("无法找到可用端口用于 OAuth 回调，请关闭占用端口的进程后重试")

        try:
            await asyncio.wait_for(callback_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass
        finally:
            server.close()
            await server.wait_closed()

        return (callback_result["code"], callback_result["state"])

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=FileTokenStorage(),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
