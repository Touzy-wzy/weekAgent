from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.response import ToolResponse


class RecallHistoryTool(Tool):
    def __init__(self):
        super().__init__(
            name="recall_history",
            description="检索历史对话记录"
        )

    def get_parameters(self):
        return [
            ToolParameter(name="op", type="string", description="操作类型: expand/search/recall_tool", required=True),
            ToolParameter(name="lo", type="integer", description="起始 seq（expand 用）", required=False),
            ToolParameter(name="hi", type="integer", description="结束 seq（expand 用）", required=False),
            ToolParameter(name="query", type="string", description="搜索关键词（search 用）", required=False),
            ToolParameter(name="k", type="integer", description="最大结果数（search 用）", required=False, default=10),
        ]

    def run(self, parameters):
        op = parameters.get("op", "")

        if op == "expand":
            # 返回指定 seq 范围的历史
            lo = parameters.get("lo", 0)
            hi = parameters.get("hi", 100)
            # TODO: 实际实现需要从 SQLiteHistoryStore 读取
            return ToolResponse.success(text=f"Expand seq {lo}-{hi}")

        elif op == "search":
            # 按关键词搜索历史
            query = parameters.get("query", "")
            k = parameters.get("k", 10)
            # TODO: 实际实现需要从 SQLiteHistoryStore 搜索
            return ToolResponse.success(text=f"Search: {query}, max {k} results")

        elif op == "recall_tool":
            # 按 tool_call_id 回溯
            tool_call_id = parameters.get("tool_call_id", "")
            # TODO: 实际实现
            return ToolResponse.success(text=f"Recall tool: {tool_call_id}")

        else:
            return ToolResponse.error(code="INVALID_PARAM", message=f"Unknown op: {op}")
