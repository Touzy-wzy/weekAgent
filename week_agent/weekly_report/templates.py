"""周报模板字段 schema 与枚举常量

模板文件：工作周报-王兆阳-2026.7.24.xlsx
布局（Sheet1，5 列 A-E）：
- 本周工作表：行 4-8，列 [序号, 分类, 任务描述, 状态, 备注/问题]
- 下周计划表：行 12-16，列 [序号, 分类, 任务描述, 状态, 风险]
- 行业信息收集表：行 21-25，列 [序号, 信息内容(B-D 合并), 备注]
"""

from pathlib import Path

# 模板文件路径（项目根目录）
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
WEEKLY_TEMPLATE_PATH = PROJECT_ROOT / "工作周报-王兆阳-2026.7.24.xlsx"

# 数据验证枚举值（与模板下拉列表一致）
CATEGORY_ENUM = ["61850", "AI", "其他"]
THIS_WEEK_STATUS_ENUM = ["已完成", "进行中", "已延期"]
NEXT_WEEK_STATUS_ENUM = ["完成", "开展", "延期"]

# 三个表格的行范围与列映射
TEMPLATE_LAYOUT = {
    "this_week_work": {
        "rows": range(4, 9),  # 行 4-8
        "columns": {"category": "B", "task": "C", "status": "D", "remark": "E"},
        "max_rows": 5,
    },
    "next_week_plan": {
        "rows": range(12, 17),  # 行 12-16
        "columns": {"category": "B", "task": "C", "status": "D", "risk": "E"},
        "max_rows": 5,
    },
    "industry_info": {
        "rows": range(21, 26),  # 行 21-25
        "columns": {"content": "B", "remark": "E"},  # B-D 合并写入 B
        "max_rows": 5,
    },
}

# 周报结构 schema（用于 LLM 输出约束）
WEEKLY_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "this_week_work": {
            "type": "array",
            "description": "本周工作条目列表",
            "max_items": 5,
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": CATEGORY_ENUM,
                        "description": "分类",
                    },
                    "task": {
                        "type": "string",
                        "description": "任务描述",
                    },
                    "status": {
                        "type": "string",
                        "enum": THIS_WEEK_STATUS_ENUM,
                        "description": "状态",
                    },
                    "remark": {
                        "type": "string",
                        "description": "备注/问题",
                    },
                },
                "required": ["category", "task", "status"],
            },
        },
        "next_week_plan": {
            "type": "array",
            "description": "下周计划条目列表",
            "max_items": 5,
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": CATEGORY_ENUM,
                        "description": "分类",
                    },
                    "task": {
                        "type": "string",
                        "description": "任务描述",
                    },
                    "status": {
                        "type": "string",
                        "enum": NEXT_WEEK_STATUS_ENUM,
                        "description": "状态",
                    },
                    "risk": {
                        "type": "string",
                        "description": "风险",
                    },
                },
                "required": ["category", "task", "status"],
            },
        },
        "industry_info": {
            "type": "array",
            "description": "行业信息收集条目列表",
            "max_items": 5,
            "items": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "信息内容",
                    },
                    "remark": {
                        "type": "string",
                        "description": "备注",
                    },
                },
                "required": ["content"],
            },
        },
    },
    "required": ["this_week_work", "next_week_plan", "industry_info"],
}


def validate_weekly_data(data: dict) -> list[str]:
    """校验周报数据是否符合模板 schema

    Args:
        data: LLM 生成的周报数据

    Returns:
        错误信息列表，空列表表示通过
    """
    errors = []

    for section in ["this_week_work", "next_week_plan", "industry_info"]:
        if section not in data:
            errors.append(f"缺少字段: {section}")
            continue

        items = data[section]
        if not isinstance(items, list):
            errors.append(f"字段 {section} 必须是数组")
            continue

        layout = TEMPLATE_LAYOUT[section]
        if len(items) > layout["max_rows"]:
            errors.append(
                f"字段 {section} 超过最大行数 {layout['max_rows']}（实际 {len(items)}）"
            )

        # 校验枚举值
        for i, item in enumerate(items, 1):
            if section == "this_week_work":
                if item.get("category") and item["category"] not in CATEGORY_ENUM:
                    errors.append(
                        f"本周工作第 {i} 项 category 非法: {item['category']}，"
                        f"允许 {CATEGORY_ENUM}"
                    )
                if item.get("status") and item["status"] not in THIS_WEEK_STATUS_ENUM:
                    errors.append(
                        f"本周工作第 {i} 项 status 非法: {item['status']}，"
                        f"允许 {THIS_WEEK_STATUS_ENUM}"
                    )
            elif section == "next_week_plan":
                if item.get("category") and item["category"] not in CATEGORY_ENUM:
                    errors.append(
                        f"下周计划第 {i} 项 category 非法: {item['category']}，"
                        f"允许 {CATEGORY_ENUM}"
                    )
                if item.get("status") and item["status"] not in NEXT_WEEK_STATUS_ENUM:
                    errors.append(
                        f"下周计划第 {i} 项 status 非法: {item['status']}，"
                        f"允许 {NEXT_WEEK_STATUS_ENUM}"
                    )

    return errors
