"""FlowUs 数据解析工具函数"""

import json
import re
from typing import Any


# 匹配 FlowUs 页面内嵌的子页面链接
_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://flowus\.cn/([a-f0-9\-]{36})\)")


def extract_content(result: Any) -> Any:
    """从 MCP CallToolResult 中提取文本内容

    支持将单个 JSON 文本自动解析为 dict/list。
    """
    if result is None:
        return None
    if hasattr(result, "content") and result.content:
        texts = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
            elif hasattr(item, "data"):
                texts.append(str(item.data))
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except (json.JSONDecodeError, TypeError):
                return texts[0]
        return texts
    return str(result)


def extract_page_ids(data: Any) -> list[str]:
    """从搜索结果中提取页面 ID 列表"""
    ids: list[str] = []
    if not data:
        return ids
    if isinstance(data, dict):
        results = data.get("results") or data.get("data") or []
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    pid = item.get("page_id") or item.get("id")
                    if pid and isinstance(pid, str):
                        ids.append(pid)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                pid = item.get("page_id") or item.get("id")
                if pid and isinstance(pid, str):
                    ids.append(pid)
    return ids


def parse_page_links(md_text: str) -> list[dict]:
    """从 Markdown 文本中解析子页面链接

    返回 [{"id": page_id, "title": title, "type": "page"}, ...]
    """
    pages: list[dict] = []
    seen: set[str] = set()
    for m in _LINK_RE.finditer(md_text):
        title = m.group(1).strip()
        page_id = m.group(2)
        if page_id not in seen:
            seen.add(page_id)
            pages.append({"id": page_id, "title": title, "type": "page"})
    return pages


def extract_block_title(block: dict) -> str:
    """从 block 对象中提取标题文本"""
    block_type = block.get("type", "")
    if block_type == "child_page":
        return block.get("child_page", {}).get("title", "")
    title_data = block.get(block_type, {})
    if isinstance(title_data, dict):
        rich_text = title_data.get("rich_text") or title_data.get("title") or []
        if isinstance(rich_text, list):
            texts = []
            for rt in rich_text:
                if isinstance(rt, dict):
                    t = rt.get("text") or rt.get("plain_text") or {}
                    if isinstance(t, dict):
                        texts.append(t.get("content", ""))
                    elif isinstance(t, str):
                        texts.append(t)
            return "".join(texts)
    return ""


def extract_tool_result(result: dict) -> Any:
    """从 MCP tools/call HTTP 响应中提取文本内容并解析 JSON

    HTTP 客户端返回的是 JSON-RPC 响应 dict：
    {"result": {"content": [{"text": "..."}]}}
    """
    try:
        text = result["result"]["content"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        return None
