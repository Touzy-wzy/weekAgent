# -*- coding: utf-8 -*-
"""告警输出（多渠道）

渠道：
- ConsoleChannel：控制台 / 存档
- MailChannel：邮件汇总（默认每天只发一封，通过 sent marker 去重）
- WecomChannel: 企业微信群机器人 webhook（每条 critical 实时推）

设计要点：
- 统一 BaseChannel 接口，send(alert)
- get_alerter() 按 config.ALERT_CHANNELS 返回多个渠道实例
- 每个渠道独立 try/except，单个失败不影响其他（批量优雅降级）
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from . import config


class BaseChannel(ABC):
    """告警渠道抽象基类"""

    name: str = "base"

    @abstractmethod
    def send(self, alert: Dict[str, Any]) -> bool:
        """发送一条告警，成功返回 True，失败返回 False（由调用方统一降级）"""


# ---------------------------------------------------------------------------
# 控制台
# ---------------------------------------------------------------------------
class ConsoleChannel(BaseChannel):
    name = "console"

    _SEVERITY_ICON = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }

    def send(self, alert: Dict[str, Any]) -> bool:
        severity = alert.get("severity", "info")
        icon = self._SEVERITY_ICON.get(severity, "📣")
        title = alert.get("title", "日志告警")
        summary = alert.get("summary", "")
        time = alert.get("time", "-")
        print(f"\n{'=' * 64}")
        print(f"{icon} [{severity.upper()}] {title}")
        print(f"   时间: {time}")
        if summary:
            print(f"   摘要: {summary}")
        body = alert.get("body", "")
        if body:
            print(f"   详情:\n{body}")
        print(f"{'=' * 64}\n")
        return True


# ---------------------------------------------------------------------------
# 邮件
# ---------------------------------------------------------------------------
class MailChannel(BaseChannel):
    """邮件告警渠道

    复用项目的 AgentlySendMailTool（自动走 compose→confirm→send 两阶段确认）。
    默认 daily 频率：每天只发一封汇总邮件（用 reports/ 下的日期 marker 去重）。
    """

    name = "mail"

    def __init__(self, to: Optional[str] = None, frequency: str | None = None):
        self.to = to or config.MAIL_TO
        self.frequency = frequency or config.MAIL_FREQUENCY
        # marker 目录：reports/.mail_sent/<YYYY-MM-DD>
        self.marker_root = config.REPORT_DIR / ".mail_sent"

    def _already_sent_today(self) -> bool:
        if self.frequency != "daily":
            return False
        today = date.today().isoformat()
        return (self.marker_root / today).exists()

    def _mark_sent(self) -> None:
        if self.frequency != "daily":
            return
        self.marker_root.mkdir(parents=True, exist_ok=True)
        (self.marker_root / date.today().isoformat()).touch()

    def send(self, alert: Dict[str, Any]) -> bool:
        if self._already_sent_today():
            print("[mail] 今日已发送过汇总邮件，跳过（daily 频率去重）")
            return True

        subject = (
            f"{alert.get('title', '日志告警')} "
            f"{alert.get('time', '')}"
        )
        # 正文复用报告落盘内容；无则用 alert.body
        body = alert.get("body", "")
        header = (
            f"{alert.get('summary', '')}\n\n"
            f"渠道: {alert.get('title', '')} | 级别: {alert.get('severity', '')} | 时间: {alert.get('time', '')}\n\n"
        )
        full_body = header + body

        try:
            from week_agent.agent.tools.agently_mail_tools import AgentlySendMailTool

            tool = AgentlySendMailTool()
            resp = tool.run({"to": self.to, "subject": subject, "body": full_body})
            if resp.status.name == "SUCCESS":
                print(f"[mail] ✅ 邮件已发送至 {self.to}")
                # 只有真正发成功才标记今日，避免丢汇总
                self._mark_sent()
                return True
            print(f"[mail] ⚠️ 发送未成功: {resp.status} {getattr(resp, 'message', '')}")
            return False
        except Exception as e:
            print(f"[mail] ❌ 发送失败: {e}")
            return False


# ---------------------------------------------------------------------------
# 企业微信 webhook
# ---------------------------------------------------------------------------
class WecomChannel(BaseChannel):
    """企业微信群机器人 webhook 渠道

    每条 critical 实时推：把告警正文整理成 markdown 消息 POST 到群机器人。
    ftpmin_severity 控制只推达标级别。
    """

    name = "wecom"

    def __init__(self, url: Optional[str] = None, min_severity: str | None = None):
        self.url = url or config.WECOM_WEBHOOK_URL
        self.min_severity = min_severity or config.WECOM_MIN_SEVERITY

    @staticmethod
    def _severity_rank(s: str) -> int:
        return {"info": 0, "warning": 1, "critical": 2}.get(s, 0)

    def send(self, alert: Dict[str, Any]) -> bool:
        sev = alert.get("severity", "info")
        # 只推不低于 min_severity 的（默认 critical）
        if self._severity_rank(sev) < self._severity_rank(self.min_severity):
            print(f"[wecom] 级别 {sev} < {self.min_severity}，跳过 webhook")
            return True

        icon = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(sev, "📣")
        content = (
            f"### {icon} {alert.get('title', '日志告警')}\n"
            f"> 级别: **{sev.upper()}** | 时间: {alert.get('time', '')}\n"
            f"> {alert.get('summary', '')}\n\n"
            f"{alert.get('body', '')}[:1280]"
        )
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        try:
            resp = httpx.post(self.url, json=payload, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("errcode") == 0:
                print(f"[wecom] ✅ 已推送至企业微信群")
                return True
            print(f"[wecom] ⚠️ 推送失败: errcode={data.get('errcode')} {data.get('errmsg')}")
            return False
        except Exception as e:
            print(f"[wecom] ❌ 推送异常: {e}")
            return False


# ---------------------------------------------------------------------------
# 渠道分发
# ---------------------------------------------------------------------------
def get_alerter(channels: list[str] | None = None) -> List[BaseChannel]:
    """按配置返回多个告警渠道实例（每个渠道独立降级）"""
    names = channels or config.ALERT_CHANNELS
    registry = {
        "console": ConsoleChannel,
        "mail": MailChannel,
        "wecom": WecomChannel,
    }
    out: List[BaseChannel] = []
    for n in names:
        n = n.strip().lower()
        if n not in registry:
            print(f"[alerter] 未知渠道跳过: {n}")
            continue
        try:
            out.append(registry[n]())
        except Exception as e:
            print(f"[alerter] 初始化渠道 {n} 失败: {e}")
    return out


def dispatch_channels(alert: Dict[str, Any], channels: list[str] | None = None) -> Dict[str, bool]:
    """把一条告警发给所有配置渠道，返回 {渠道名: 是否成功}

    每个渠道独立 try/except，单个失败不影响其他（批量优雅降级）。
    """
    result: Dict[str, bool] = {}
    for ch in get_alerter(channels):
        try:
            result[ch.name] = bool(ch.send(alert))
        except Exception as e:
            print(f"[alerter] 渠道 {ch.name} send 异常: {e}")
            result[ch.name] = False
    return result


def format_alert_payload(
    severity: str,
    title: str,
    summary: str,
    body: str = "",
    when: str | None = None,
) -> Dict[str, Any]:
    """统一构造告警数据结构"""
    if when is None:
        from datetime import datetime

        when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "severity": severity,
        "title": title,
        "summary": summary,
        "body": body,
        "time": when,
    }