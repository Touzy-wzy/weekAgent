"""Web UI API 端点测试

需要先启动 Web UI: `python run.py --web`
"""

import asyncio

import httpx


async def test():
    async with httpx.AsyncClient(timeout=180) as c:
        # 测试列出页面
        print("=== GET /api/pages ===")
        r = await c.get("http://127.0.0.1:8000/api/pages")
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Pages count: {len(data)}")
        for p in data[:8]:
            print(f"  [{p['type']}] {p['title']}  (id={p['id'][:24]}...)")
        if len(data) > 8:
            print(f"  ... and {len(data) - 8} more")

        if not data:
            print("No pages found!")
            return

        # 测试获取页面内容
        first_page = data[0]
        print(f"\n=== GET /api/page/{first_page['id'][:24]}... ===")
        print(f"Title: {first_page['title']}")
        r2 = await c.get(f"http://127.0.0.1:8000/api/page/{first_page['id']}")
        print(f"Status: {r2.status_code}")
        content = r2.json()
        html_len = len(content.get("html", ""))
        md_len = len(content.get("markdown", ""))
        print(f"HTML length: {html_len}")
        print(f"Markdown length: {md_len}")
        print(f"Markdown preview (first 200 chars):")
        print(content.get("markdown", "")[:200])

        # 测试搜索
        print(f"\n=== GET /api/search?q=会议 ===")
        r3 = await c.get("http://127.0.0.1:8000/api/search", params={"q": "会议"})
        print(f"Status: {r3.status_code}")
        search_data = r3.json()
        print(f"Results: {len(search_data.get('results', []))}")


if __name__ == "__main__":
    asyncio.run(test())
