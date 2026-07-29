"""Excel 填写工具 - 把周报数据填入 xlsx 模板"""

import json
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

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
                "返回生成的 xlsx 文件路径。"
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
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        reporter_name = parameters.get("reporter_name", "").strip()
        week_range = parameters.get("week_range", "").strip()
        report_data_str = parameters.get("report_data", "").strip()

        if not reporter_name or not week_range or not report_data_str:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="reporter_name、week_range、report_data 都不能为空",
            )

        print(f"📊 [fill_weekly_excel] {reporter_name} / {week_range}")
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

        try:
            output_path = fill_weekly_report(
                reporter_name=reporter_name,
                week_range=week_range,
                this_week_work=full_data["this_week_work"],
                next_week_plan=full_data["next_week_plan"],
                industry_info=full_data["industry_info"],
            )
            print(f"  ✅ 生成: {output_path}")
            return ToolResponse.success(
                text=f"周报 xlsx 已生成: {output_path}",
                data={
                    "reporter_name": reporter_name,
                    "week_range": week_range,
                    "xlsx_path": str(output_path),
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
