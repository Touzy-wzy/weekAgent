"""常用收件人管理工具

把原周报助手页面"常用收件人"功能改为工具暴露给 Agent。
收件人列表保存在 data/recipients.json，与历史页面格式兼容。
"""

import json
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

from week_agent.config import DATA_DIR

RECIPIENTS_FILE = DATA_DIR / "recipients.json"


def _read_recipients() -> list[dict]:
    """读取常用收件人列表"""
    if not RECIPIENTS_FILE.exists():
        return []
    try:
        return json.loads(RECIPIENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_recipients(data: list[dict]):
    """写入常用收件人列表"""
    RECIPIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECIPIENTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class ListRecipientsTool(Tool):
    """查询常用收件人列表"""

    def __init__(self):
        super().__init__(
            name="list_recipients",
            description=(
                "查询用户的常用收件人列表（姓名 + 邮箱）。"
                "用于发邮件前让用户挑选收件人，或用户询问有哪些常用收件人时调用。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return []

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        recipients = _read_recipients()
        if not recipients:
            return ToolResponse.success(
                text="常用收件人列表为空，请用户提供邮箱地址",
                data={"recipients": []},
            )
        lines = [f"- {r.get('name', '')} <{r.get('email', '')}>" for r in recipients]
        return ToolResponse.success(
            text=f"常用收件人共 {len(recipients)} 个：\n" + "\n".join(lines),
            data={"recipients": recipients},
        )


class AddRecipientTool(Tool):
    """添加常用收件人"""

    def __init__(self):
        super().__init__(
            name="add_recipient",
            description=(
                "添加一个常用收件人（姓名 + 邮箱），保存到收件人列表供以后使用。"
                "用户说'记一下张三的邮箱 xxx'或'添加常用收件人'时调用。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="name",
                type="string",
                description="收件人姓名",
                required=True,
            ),
            ToolParameter(
                name="email",
                type="string",
                description="收件人邮箱",
                required=True,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        name = str(parameters.get("name", "")).strip()
        email = str(parameters.get("email", "")).strip()
        if not email:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="email 不能为空",
            )
        if not name:
            name = email.split("@")[0]

        recipients = _read_recipients()
        # 去重
        if any(r.get("email") == email for r in recipients):
            return ToolResponse.success(
                text=f"收件人 {name} <{email}> 已存在，无需重复添加",
                data={"recipients": recipients},
            )
        recipients.append({"name": name, "email": email})
        _write_recipients(recipients)
        return ToolResponse.success(
            text=f"已添加常用收件人：{name} <{email}>",
            data={"recipients": recipients},
        )
