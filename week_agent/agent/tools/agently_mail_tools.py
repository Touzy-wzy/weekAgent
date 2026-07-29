"""Agently CLI 邮件工具 - 封装邮件发送功能为 hello-agents 工具

单工具设计：AgentlySendMailTool
- 一次调用内部完成 agently-cli 的两阶段确认（compose → confirm → send）
- LLM 只需提供邮件内容，无需管理 confirmation_token
- 自动处理附件相对路径（agently-cli 要求相对路径，需切换工作目录）

Windows 兼容：agently-cli 是 npm 全局安装的 .cmd 脚本，
subprocess.run 不带 shell=True 时需用 shutil.which() 解析完整路径。
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse


def _resolve_agently_cli() -> Optional[str]:
    """解析 agently-cli 完整路径（Windows 下包含 .cmd 扩展名）"""
    return shutil.which("agently-cli")


def _run_agently_send(
    to: str,
    subject: str,
    body: str,
    attachment: str = "",
    confirmation_token: str = "",
    cwd: Optional[str] = None,
) -> dict:
    """调用 agently-cli 发送邮件，返回解析后的 JSON 响应

    Args:
        cwd: 工作目录（附件路径需相对此目录）

    Raises:
        RuntimeError: 命令执行失败
    """
    cli_exe = _resolve_agently_cli()
    if not cli_exe:
        raise RuntimeError("agently-cli 未安装或不在 PATH 中")

    # --to 是 stringArray，多个收件人需重复 --to
    to_list = [t.strip() for t in to.split(",") if t.strip()]
    cmd = [cli_exe, "message", "+send"]
    for t in to_list:
        cmd.extend(["--to", t])
    cmd.extend(["--subject", subject, "--body", body])

    if attachment:
        # agently-cli 要求相对路径，若传入绝对路径则转换为相对 cwd 的路径
        if cwd:
            att_path = Path(attachment)
            try:
                rel = att_path.relative_to(cwd)
                cmd.extend(["--attachment", str(rel)])
            except ValueError:
                # 不在 cwd 子树内，用文件名（依赖 cwd 设置）
                cmd.extend(["--attachment", att_path.name])
        else:
            cmd.extend(["--attachment", attachment])

    if confirmation_token:
        cmd.extend(["--confirmation-token", confirmation_token])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )

    if result.returncode != 0:
        raise RuntimeError(f"agently-cli failed: {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"agently-cli 返回非 JSON: {result.stdout[:200]}")


class AgentlySendMailTool(Tool):
    """发送邮件工具 - 一次调用完成两阶段确认

    内部自动调用 agently-cli 两次：
    1. 第一次调用获取 confirmation_token
    2. 第二次调用用 token 真正发送

    LLM 只需提供 to/subject/body/attachment，无需管理 token。
    """

    def __init__(self):
        super().__init__(
            name="agently_send_mail",
            description=(
                "发送邮件（自动完成确认流程）。"
                "提供收件人、主题、正文即可发送，支持附件。"
                "无需手动管理确认令牌，工具内部自动处理。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="to",
                type="string",
                description="收件人邮箱地址，多个邮箱用逗号分隔 (如: a@example.com,b@example.com)",
                required=True,
            ),
            ToolParameter(
                name="subject",
                type="string",
                description="邮件主题",
                required=True,
            ),
            ToolParameter(
                name="body",
                type="string",
                description="邮件内容（正文）",
                required=True,
            ),
            ToolParameter(
                name="attachment",
                type="string",
                description="附件文件路径（可选，如周报 xlsx 路径，绝对或相对路径均可）",
                required=False,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        to = parameters.get("to", "").strip()
        subject = parameters.get("subject", "").strip()
        body = parameters.get("body", "").strip()
        attachment = parameters.get("attachment", "").strip()

        # 参数校验
        if not to:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="收件人 (to) 不能为空",
            )
        if not subject:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="邮件主题 (subject) 不能为空",
            )
        if not body:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="邮件内容 (body) 不能为空",
            )

        print(f"[send_mail] Sending email")
        print(f"   To: {to}")
        print(f"   Subject: {subject}")
        if attachment:
            print(f"   Attachment: {attachment}")

        # 确定工作目录：附件所在目录（agently-cli 要求附件为相对路径）
        cwd = None
        if attachment:
            att_path = Path(attachment)
            if att_path.exists():
                cwd = str(att_path.parent)
                print(f"   CWD (for relative attachment): {cwd}")
            else:
                print(f"   ⚠️ 附件文件不存在: {attachment}，将尝试继续发送")

        try:
            # 阶段 1：第一次调用，获取 confirmation_token
            print(f"   [1/2] 预提交邮件，获取确认令牌...")
            resp1 = _run_agently_send(
                to=to,
                subject=subject,
                body=body,
                attachment=attachment,
                confirmation_token="",
                cwd=cwd,
            )

            data1 = resp1.get("data", {})
            if not data1.get("confirmation_required"):
                # 不需要确认，可能已直接发送
                if data1.get("queued") or data1.get("sent"):
                    print(f"  [OK] Mail sent directly (no confirmation needed)")
                    return ToolResponse.success(
                        text=self._format_success(to, subject, "Sent"),
                        data={"queued": True, "to": to, "subject": subject},
                    )
                # 异常响应
                raise RuntimeError(
                    f"Unexpected response: {data1.get('message', resp1)}"
                )

            token = data1.get("confirmation_token", "")
            summary = data1.get("summary", {})
            if not token:
                raise RuntimeError(f"No confirmation_token in response: {data1}")

            print(f"   [1/2] Got token: {token[:20]}...")
            print(f"         Summary: to={summary.get('to')}, subject={summary.get('subject')}, attachments={summary.get('attachment_count')}")

            # 阶段 2：第二次调用，用 token 真正发送
            print(f"   [2/2] 提交确认令牌，发送邮件...")
            resp2 = _run_agently_send(
                to=to,
                subject=subject,
                body=body,
                attachment=attachment,
                confirmation_token=token,
                cwd=cwd,
            )

            data2 = resp2.get("data", {})
            if data2.get("queued") or data2.get("sent") or resp2.get("ok"):
                print(f"  [OK] Mail sent successfully")
                return ToolResponse.success(
                    text=self._format_success(to, subject, "Sent"),
                    data={
                        "queued": True,
                        "to": to,
                        "subject": subject,
                        "attachment": attachment or None,
                    },
                )
            else:
                raise RuntimeError(
                    f"Send failed after confirmation: {data2.get('message', resp2)}"
                )

        except subprocess.TimeoutExpired:
            print(f"  [ERROR] Timeout")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message="邮件发送超时，请重试",
            )
        except Exception as e:
            print(f"  [ERROR] {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"邮件发送失败: {str(e)}",
            )

    def _format_success(self, to: str, subject: str, status: str) -> str:
        return (
            f"[OK] 邮件发送成功！\n"
            f"- 收件人: {to}\n"
            f"- 主题: {subject}\n"
            f"- 状态: {status}\n"
        )


class AgentlyComposeMailTool(Tool):
    """编写邮件工具 - 仅预览，不发送（保留兼容性，推荐用 AgentlySendMailTool）

    返回预览信息，但不发送。LLM 应优先使用 agently_send_mail 直接发送。
    """

    def __init__(self):
        super().__init__(
            name="agently_compose_mail",
            description=(
                "预览邮件内容（不发送）。"
                "如需发送邮件，请直接使用 agently_send_mail 工具，它会自动完成确认流程。"
                "本工具仅用于查看邮件预览。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="to",
                type="string",
                description="收件人邮箱地址，多个邮箱用逗号分隔",
                required=True,
            ),
            ToolParameter(
                name="subject",
                type="string",
                description="邮件主题",
                required=True,
            ),
            ToolParameter(
                name="body",
                type="string",
                description="邮件内容（正文）",
                required=True,
            ),
            ToolParameter(
                name="attachment",
                type="string",
                description="附件文件路径（可选）",
                required=False,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        to = parameters.get("to", "").strip()
        subject = parameters.get("subject", "").strip()
        body = parameters.get("body", "").strip()
        attachment = parameters.get("attachment", "").strip()

        if not to or not subject or not body:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="收件人、主题、正文都不能为空",
            )

        print(f"[compose_mail] Preview (not sending)")
        print(f"   To: {to}")
        print(f"   Subject: {subject}")
        print(f"   Content length: {len(body)} chars")
        if attachment:
            print(f"   Attachment: {attachment}")

        return ToolResponse.success(
            text=(
                f"[预览] 邮件内容如下（未发送）：\n"
                f"- 收件人: {to}\n"
                f"- 主题: {subject}\n"
                f"- 正文长度: {len(body)} 字符\n"
                f"- 附件: {attachment or '无'}\n\n"
                f"如需发送，请使用 agently_send_mail 工具。"
            ),
            data={
                "to": to,
                "subject": subject,
                "body": body,
                "attachment": attachment or None,
            },
        )
