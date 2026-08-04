"""从 ToolRegistry 自动生成工具摘要文本，供系统提示词使用。

解决的问题：工具描述不再手写在提示词里，改为从 Tool 对象动态生成，
与 function calling schema 保持单一真相源。
"""

from typing import List, Dict, Any


def build_tool_summary(tools: List[Dict[str, Any]]) -> str:
    """从 tool schemas 列表生成人类可读的工具摘要。

    输出示例::

        ## 可用工具

        1. **flowus_search**: 语义搜索 FlowUs 工作空间
           参数: query*: 搜索关键词
        2. **flowus_list_pages**: 列出某个项目下的所有子页面
           参数: project_name*: 项目名称

    Args:
        tools: ``ToolRegistry`` 导出的 JSON Schema 列表，
               每项为 ``{"type": "function", "function": {...}}`` 格式。

    Returns:
        格式化的工具摘要字符串。
    """
    if not tools:
        return "## 可用工具\n\n暂无可用工具。"

    # 过滤掉内置工具（Thought / Finish），只保留业务工具
    business_tools = [
        t for t in tools
        if t.get("function", {}).get("name") not in ("Thought", "Finish")
    ]

    if not business_tools:
        return "## 可用工具\n\n暂无业务工具。"

    lines: List[str] = ["## 可用工具", ""]

    for i, schema in enumerate(business_tools, 1):
        func = schema.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        params = func.get("parameters", {}).get("properties", {})
        required = func.get("parameters", {}).get("required", [])

        # 参数行
        param_parts: List[str] = []
        for pname, pdef in params.items():
            tag = "*" if pname in required else ""
            p_desc = pdef.get("description", "")
            param_parts.append(f"{pname}{tag}: {p_desc}")

        params_line = "参数: " + ", ".join(param_parts) if param_parts else "（无参数）"

        lines.append(f"{i}. **{name}**: {desc}")
        lines.append(f"   {params_line}")

    return "\n".join(lines)
