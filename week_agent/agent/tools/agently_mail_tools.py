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
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse


def _resolve_agently_cli() -> Optional[str]:
    """解析 agently-cli 完整路径（Windows 下包含 .cmd 扩展名）"""
    return shutil.which("agently-cli")


def _get_drafts_dir() -> Path:
    """获取周报草稿目录"""
    # 从当前文件位置推算项目根目录：week_agent/agent/tools/ -> 项目根
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "data" / "drafts"


def _list_available_attachments() -> str:
    """列出 drafts 目录下可用的 xlsx 文件，供 LLM 选择"""
    drafts = _get_drafts_dir()
    if not drafts.exists():
        return f"  (目录不存在: {drafts})"
    files = sorted(drafts.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return f"  (目录 {drafts} 下无 xlsx 文件)"
    lines = [f"  - {f.name}  ({f.stat().st_size // 1024} KB, {datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')})" for f in files[:10]]
    return "\n".join(lines)


def _resolve_attachment(attachment: str) -> Optional[Path]:
    """模糊匹配附件路径

    支持的场景：
    - LLM 传了文件名片段（如 "28.xlsx"、"周礼"）
    - LLM 传了相对文件名（如 "工作周报-周礼-2026.7.28.xlsx"）

    Returns:
        匹配到的完整 Path，或 None
    """
    att = attachment.strip()
    drafts = _get_drafts_dir()

    # 1. 先尝试直接作为路径解析
    p = Path(att)
    if p.exists():
        return p

    # 2. 在 drafts 目录下查找
    if not drafts.exists():
        return None

    # 2a. 精确文件名匹配
    direct = drafts / att
    if direct.exists():
        return direct

    # 2b. 模糊匹配：提取关键片段（日期、姓名）
    files = list(drafts.glob("*.xlsx"))
    if not files:
        return None

    # 提取 attachment 中的关键信息
    att_lower = att.lower()

    # 尝试匹配日期片段（如 "28" -> "2026.7.28"）
    import re
    date_match = re.search(r'(\d{1,2})\.xlsx', att)
    date_day = date_match.group(1) if date_match else None

    for f in files:
        fname = f.name.lower()
        # 精确文件名包含
        if att_lower in fname:
            return f
        # 日期片段匹配（如 "28.xlsx" 匹配 "...2026.7.28.xlsx"）
        if date_day and f".{date_day}.xlsx" in fname:
            return f
        # 日期片段匹配（如 "28.xlsx" 匹配 "...7.28.xlsx"）
        if date_day and f"{date_day}.xlsx" in fname and not fname.endswith(f"-{date_day}.xlsx"):
            # 确保不是误匹配，优先最近修改的
            pass

    # 2c. 按修改时间排序，如果有多个匹配取最新的
    matches = []
    for f in files:
        fname = f.name.lower()
        if att_lower in fname:
            matches.append(f)
        elif date_day and f".{date_day}.xlsx" in fname:
            matches.append(f)

    if matches:
        return sorted(matches, key=lambda f: f.stat().st_mtime, reverse=True)[0]

    return None


def _run_agently_send(
    to: str,
    subject: str,
    body: str,
    attachment: str = "",
    confirmation_token: str = "",
    cwd: Optional[str] = None,
    temp_attachment: Optional[Path] = None,
    body_file: Optional[Path] = None,
) -> dict:
    """调用 agently-cli 发送邮件，返回解析后的 JSON 响应

    Args:
        cwd: 工作目录（附件路径需相对此目录）
        temp_attachment: 临时附件路径（英文名，避免中文编码问题）。
            如果提供，则使用此路径作为附件，忽略 attachment 参数。
        body_file: body 文件路径（相对 cwd）。
            如果提供，用 --body-file 替代 --body，避免长 body/换行符破坏命令行解析。

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
    cmd.extend(["--subject", subject])

    # body 处理：优先用 --body-file（避免长 body/换行符/特殊字符破坏命令行解析）
    if body_file and body_file.exists():
        # body_file 应该是相对 cwd 的路径
        try:
            rel_body = body_file.relative_to(cwd) if cwd else body_file.name
            cmd.extend(["--body-file", str(rel_body)])
            print(f"   [debug] body 参数: --body-file {rel_body}")
        except ValueError:
            cmd.extend(["--body-file", body_file.name])
            print(f"   [debug] body 参数: --body-file {body_file.name}")
    else:
        cmd.extend(["--body", body])
        print(f"   [debug] body 参数: --body (len={len(body)})")

    # 附件处理：优先使用临时英文文件名（避免中文编码问题）
    if temp_attachment and temp_attachment.exists():
        # 临时文件已在 cwd 下，用相对文件名
        att_arg = temp_attachment.name
        cmd.extend(["--attachment", att_arg])
        print(f"   [debug] 附件参数: {att_arg}")
    elif attachment:
        att_arg = attachment
        if cwd:
            att_path = Path(attachment)
            try:
                rel = att_path.relative_to(cwd)
                att_arg = str(rel)
            except ValueError:
                att_arg = att_path.name
        cmd.extend(["--attachment", att_arg])
        print(f"   [debug] 附件参数(原始): {att_arg}")

    if confirmation_token:
        cmd.extend(["--confirmation-token", confirmation_token])

    # 简化调试日志：只打印参数数量和关键参数
    print(f"   [debug] CMD 参数数量: {len(cmd)}, CWD: {cwd}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
        encoding="utf-8",
    )

    if result.returncode != 0:
        raise RuntimeError(f"agently-cli failed (code={result.returncode}): {result.stderr.strip()}")

    try:
        resp = json.loads(result.stdout)
        summary = resp.get("data", {}).get("summary", {})
        if summary:
            print(f"   [debug] summary: attachments={summary.get('attachment_count')}, subject={summary.get('subject', '')[:30]}")
        return resp
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

        # 解析附件路径（支持模糊匹配）
        resolved_att_path = None
        if attachment:
            att_path = Path(attachment)
            if att_path.exists():
                resolved_att_path = att_path
            else:
                # 附件不存在，尝试在 drafts 目录模糊匹配
                resolved = _resolve_attachment(attachment)
                if resolved:
                    resolved_att_path = resolved
                    print(f"   ✅ 模糊匹配到附件: {resolved_att_path.name}")
                else:
                    # 列出可用文件，帮助 LLM 选择正确路径
                    available = _list_available_attachments()
                    return ToolResponse.error(
                        code=ToolErrorCode.INVALID_PARAM,
                        message=(
                            f"附件文件不存在: {attachment}\n"
                            f"请使用 fill_weekly_excel 工具返回的完整 xlsx_path。\n"
                            f"可用文件列表:\n{available}"
                        ),
                    )

        # 关键修复：将附件和body都放到临时目录
        # 1. body 用 --body-file 传递，避免长 body/换行符/特殊字符破坏命令行解析
        # 2. 附件复制到临时目录，保留中文名，失败回退英文名
        temp_dir = Path(tempfile.mkdtemp(prefix="agently_mail_"))
        cwd = str(temp_dir)

        # 写入 body 文件（UTF-8）
        body_file = temp_dir / "body.html"
        body_file.write_text(body, encoding="utf-8")
        print(f"   📝 body 已写入临时文件: body.html ({len(body)} chars)")

        temp_att_path = None
        temp_att_en = None
        if resolved_att_path:
            original_name = resolved_att_path.name
            temp_att_cn = temp_dir / original_name
            temp_att_en = temp_dir / "weekly_report.xlsx"
            shutil.copy2(resolved_att_path, temp_att_cn)
            print(f"   📎 附件已复制到临时目录: {original_name}")
            temp_att_path = temp_att_cn

        try:
            # 阶段 1：第一次调用，获取 confirmation_token
            print(f"   [1/2] 预提交邮件，获取确认令牌(附件: {temp_att_path.name if temp_att_path else '无'})...")
            resp1 = _run_agently_send(
                to=to,
                subject=subject,
                body=body,
                attachment="",
                confirmation_token="",
                cwd=cwd,
                temp_attachment=temp_att_path,
                body_file=body_file,
            )

            data1 = resp1.get("data", {})
            summary1 = data1.get("summary", {})
            att_count1 = summary1.get("attachment_count", 0)

            # 降级检查：如果中文名未被识别(attachments=0)，回退到英文名重试
            if temp_att_path and att_count1 == 0 and data1.get("confirmation_required"):
                print(f"   ⚠️ 中文名未被识别(attachments=0)，回退到英文名重试...")
                shutil.copy2(resolved_att_path, temp_att_en)
                temp_att_path = temp_att_en
                resp1 = _run_agently_send(
                    to=to,
                    subject=subject,
                    body=body,
                    attachment="",
                    confirmation_token="",
                    cwd=cwd,
                    temp_attachment=temp_att_path,
                    body_file=body_file,
                )
                data1 = resp1.get("data", {})
                summary1 = data1.get("summary", {})
                att_count1 = summary1.get("attachment_count", 0)

            if not data1.get("confirmation_required"):
                if data1.get("queued") or data1.get("sent"):
                    print(f"  [OK] Mail sent directly (no confirmation needed)")
                    self._cleanup_temp(temp_dir)
                    return ToolResponse.success(
                        text=self._format_success(to, subject, "Sent"),
                        data={"queued": True, "to": to, "subject": subject},
                    )
                raise RuntimeError(
                    f"Unexpected response: {data1.get('message', resp1)}"
                )

            token = data1.get("confirmation_token", "")
            summary = summary1
            if not token:
                raise RuntimeError(f"No confirmation_token in response: {data1}")

            print(f"   [1/2] Got token: {token[:20]}...")
            print(f"         Summary: attachments={summary.get('attachment_count')}")

            # 阶段 2：第二次调用，用 token 真正发送
            print(f"   [2/2] 提交确认令牌，发送邮件...")
            resp2 = _run_agently_send(
                to=to,
                subject=subject,
                body=body,
                attachment="",
                confirmation_token=token,
                cwd=cwd,
                temp_attachment=temp_att_path,
                body_file=body_file,
            )

            data2 = resp2.get("data", {})
            # 严格判断发送成功：阶段 2 不应再有 confirmation_required，且 queued/sent 为 True
            # 注意：不能用 resp2.get("ok") 判断——ok:true 只表示请求被接受，不代表邮件已发送
            if data2.get("confirmation_required"):
                # 阶段 2 仍要求确认 = token 无效/过期，邮件未发送
                raise RuntimeError(
                    f"确认令牌无效，邮件未发送: {data2.get('message', data2)}"
                )
            if data2.get("queued") or data2.get("sent"):
                from_email = summary.get("from", "unknown")
                print(f"  [OK] Mail queued successfully")
                self._cleanup_temp(temp_dir)
                return ToolResponse.success(
                    text=self._format_success(to, subject, "Sent", from_email, summary.get("attachment_count", 0)),
                    data={
                        "queued": True,
                        "to": to,
                        "subject": subject,
                        "attachment": str(resolved_att_path) if resolved_att_path else None,
                        "from": from_email,
                        "raw_response": data2,
                    },
                )
            else:
                raise RuntimeError(
                    f"Send failed after confirmation, unexpected response: {data2}"
                )

        except subprocess.TimeoutExpired:
            print(f"  [ERROR] Timeout")
            self._cleanup_temp(temp_dir)
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message="邮件发送超时，请重试",
            )
        except Exception as e:
            print(f"  [ERROR] {e}")
            self._cleanup_temp(temp_dir)
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"邮件发送失败: {str(e)}",
            )

    @staticmethod
    def _cleanup_temp(temp_dir: Optional[Path]) -> None:
        """清理临时目录"""
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"   [warn] 清理临时目录失败: {e}")

    def _format_success(self, to: str, subject: str, status: str,
                        from_email: str = "", attachment_count: int = 0) -> str:
        lines = [
            f"[OK] 邮件已入队发送！",
            f"- 收件人: {to}",
            f"- 主题: {subject}",
            f"- 发件人: {from_email or '未知'}",
            f"- 附件数: {attachment_count}",
            f"- 状态: {status}",
        ]
        if from_email and "agent.qq.com" in from_email:
            lines.append("- ⚠️ 发件人为虚拟邮箱，部分企业邮箱可能拦截或归入垃圾箱，请注意查收")
        return "\n".join(lines) + "\n"


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
