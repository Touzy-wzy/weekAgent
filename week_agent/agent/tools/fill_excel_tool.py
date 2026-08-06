"""Excel 填写工具 - 把周报数据填入 xlsx 模板"""

import json
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

from week_agent.config import DATA_DIR
from week_agent.weekly_report.excel_filler import fill_weekly_report
from week_agent.weekly_report.templates import validate_weekly_data


class FillExcelTool(Tool):
    """把结构化周报数据填入 xlsx 模板，生成 .xlsx 文件"""

    def __init__(self):
        super().__init__(
            name="fill_weekly_excel",
            description=(
                "把结构化周报数据填入 xlsx 模板，生成周报 .xlsx 文件。"
                "参数 report_data 是 JSON 字符串，包含 this_week_work / next_week_plan / industry_info 三个数组。"
                "返回生成的 xlsx 文件路径（含文件名），用户可通过下载链接获取。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="reporter_name",
                type="string",
                description="填报人姓名",
                required=True,
            ),
            ToolParameter(
                name="week_range",
                type="string",
                description="周报区间，如 '2026.7.22-7.28'",
                required=True,
            ),
            ToolParameter(
                name="report_data",
                type="string",
                description=(
                    "周报数据 JSON 字符串，结构："
                    '{"this_week_work":[{"category":"AI","task":"...","status":"进行中","remark":"..."}],'
                    ' "next_week_plan":[...],'
                    ' "industry_info":[{"content":"...","remark":"..."}]}'
                    "。category 枚举 61850/AI/其他；本周 status 枚举 已完成/进行中/已延期；"
                    "下周 status 枚举 完成/开展/延期。每个数组最多 5 项。"
                ),
                required=True,
            ),
            ToolParameter(
                name="session_id",
                type="string",
                description="当前会话 ID，用于把生成的 xlsx 保存到该会话的输出目录，便于用户下载。见系统提示中的'当前会话信息'。",
                required=True,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        reporter_name = parameters.get("reporter_name", "").strip()
        week_range = parameters.get("week_range", "").strip()
        report_data_str = parameters.get("report_data", "").strip()
        session_id = str(parameters.get("session_id", "")).strip()

        if not reporter_name or not week_range or not report_data_str:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="reporter_name、week_range、report_data 都不能为空",
            )
        if not session_id:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="session_id 不能为空（用于把 xlsx 保存到会话目录供下载）",
            )

        print(f"📊 [fill_weekly_excel] {reporter_name} / {week_range} / session={session_id}")
        try:
            data = json.loads(report_data_str)
        except json.JSONDecodeError as e:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message=f"report_data 不是合法 JSON: {e}",
            )

        # 补全字段
        full_data = {
            "this_week_work": data.get("this_week_work", []),
            "next_week_plan": data.get("next_week_plan", []),
            "industry_info": data.get("industry_info", []),
        }

        # 校验
        errors = validate_weekly_data(full_data)
        if errors:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="周报数据校验失败: " + "; ".join(errors),
            )

        # 输出到会话专属目录，便于下载端点找到文件
        output_dir = DATA_DIR / "agent_outputs" / session_id
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            output_path = fill_weekly_report(
                reporter_name=reporter_name,
                week_range=week_range,
                this_week_work=full_data["this_week_work"],
                next_week_plan=full_data["next_week_plan"],
                industry_info=full_data["industry_info"],
                output_dir=output_dir,
            )
            print(f"  ✅ 生成: {output_path}")
            filename = output_path.name
            return ToolResponse.success(
                text=(
                    f"周报 xlsx 已生成。\n"
                    f"文件名: {filename}\n"
                    f"路径: {output_path}\n"
                    f"下载链接: /api/agent/sessions/{session_id}/files/{filename}"
                ),
                data={
                    "reporter_name": reporter_name,
                    "week_range": week_range,
                    "xlsx_path": str(output_path),
                    "filename": filename,
                    "session_id": session_id,
                    "download_url": f"/api/agent/sessions/{session_id}/files/{filename}",
                    "rows_filled": {
                        "this_week_work": len(full_data["this_week_work"]),
                        "next_week_plan": len(full_data["next_week_plan"]),
                        "industry_info": len(full_data["industry_info"]),
                    },
                },
            )
        except Exception as e:
            print(f"  ❌ 填写失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"Excel 填写失败: {str(e)}",
            )

