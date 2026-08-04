"""
Skill 发现与注册模块

扫描 skills/ 目录下的 SKILL.md 文件，解析 YAML frontmatter，
将其包装为 hello-agents Tool 并注册到 ToolRegistry。

SKILL.md 格式:
```markdown
---
name: skill-name
description: Use this skill when ...
trigger: keyword1, keyword2
---

# Skill Name

Instructions here...
```
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.response import ToolResponse

logger = logging.getLogger(__name__)


class SkillTool(Tool):
    """将 SKILL.md 包装为 hello-agents Tool 的适配器

    每个 SKILL.md 被包装为一个 Tool，包含:
    - name: skill 名称
    - description: skill 描述
    - trigger: 触发关键词列表
    - body: SKILL.md 的正文内容
    """

    def __init__(
        self,
        name: str,
        description: str,
        trigger: List[str],
        body: str,
        skill_path: str,
    ):
        super().__init__(name=name, description=description)
        self.trigger = trigger
        self.body = body
        self.skill_path = skill_path

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="用户查询或任务描述，用于匹配 skill 的触发条件",
                required=True,
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        query = parameters.get("query", "")
        # 检查触发关键词是否匹配
        matched = self._match_trigger(query)
        if not matched:
            return ToolResponse.partial(
                text=f"Skill '{self.name}' 未被触发。"
                f"当前查询未匹配到触发关键词: {', '.join(self.trigger)}"
            )
        # 返回 skill 内容供 Agent 参考
        return ToolResponse.success(
            text=f"已激活 Skill: {self.name}\n\n{self.body}",
            data={"skill_name": self.name, "triggered_by": matched},
        )

    def _match_trigger(self, query: str) -> Optional[str]:
        """检查查询是否匹配触发关键词，返回匹配的关键词或 None"""
        query_lower = query.lower()
        for kw in self.trigger:
            if kw.strip().lower() in query_lower:
                return kw.strip()
        return None

    def __repr__(self) -> str:
        return f"SkillTool(name={self.name!r}, trigger={self.trigger!r})"


class SkillDiscovery:
    """技能发现引擎

    扫描指定目录下的 SKILL.md 文件，解析 YAML frontmatter，
    将其包装为 Tool 并可注册到 ToolRegistry。

    使用示例:
        discovery = SkillDiscovery(skills_dir="skills")
        skills = discovery.scan_skills()
        discovery.register_skills(tool_registry)
    """

    def __init__(self, skills_dir: str = "skills"):
        """初始化技能发现引擎

        Args:
            skills_dir: skills 目录路径（相对于工作目录或绝对路径）
        """
        self.skills_dir = Path(skills_dir)
        self._discovered: List[Dict[str, Any]] = []
        self._tools: List[SkillTool] = []
        self._watching = False
        self._watch_thread = None

    def scan_skills(self) -> List[Dict[str, Any]]:
        """扫描 skills 目录，查找所有 SKILL.md 文件

        Returns:
            解析后的 skill 元数据列表，每个元素包含:
            - name: skill 名称
            - description: skill 描述
            - trigger: 触发关键词列表
            - body: SKILL.md 正文
            - path: SKILL.md 文件路径
        """
        self._discovered = []

        if not self.skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {self.skills_dir}")
            return self._discovered

        # 递归查找所有 SKILL.md 文件
        for skill_file in self.skills_dir.rglob("SKILL.md"):
            try:
                skill_meta = self.parse_skill(str(skill_file))
                if skill_meta:
                    self._discovered.append(skill_meta)
                    logger.info(f"发现 Skill: {skill_meta['name']} ({skill_file})")
            except Exception as e:
                logger.error(f"解析 SKILL.md 失败: {skill_file} - {e}")

        logger.info(f"共发现 {len(self._discovered)} 个 Skill")
        return self._discovered

    def parse_skill(self, skill_path: str) -> Optional[Dict[str, Any]]:
        """解析单个 SKILL.md 文件

        支持的 YAML frontmatter 字段:
        - name: skill 名称（必需）
        - description: skill 描述（必需）
        - trigger: 触发关键词，逗号分隔（可选，默认为空列表）

        Args:
            skill_path: SKILL.md 文件路径

        Returns:
            解析后的 skill 元数据字典，解析失败返回 None
        """
        path = Path(skill_path)
        if not path.exists():
            logger.error(f"SKILL.md 不存在: {skill_path}")
            return None

        content = path.read_text(encoding="utf-8")

        # 解析 YAML frontmatter
        frontmatter, body = self._parse_frontmatter(content)
        if not frontmatter:
            logger.warning(f"未找到 YAML frontmatter: {skill_path}")
            return None

        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")
        trigger_raw = frontmatter.get("trigger", "")

        if not name:
            logger.warning(f"SKILL.md 缺少 name 字段: {skill_path}")
            return None

        # 解析 trigger 为列表
        if isinstance(trigger_raw, str):
            trigger = [t.strip() for t in trigger_raw.split(",") if t.strip()]
        elif isinstance(trigger_raw, list):
            trigger = [str(t).strip() for t in trigger_raw if str(t).strip()]
        else:
            trigger = []

        return {
            "name": name,
            "description": description,
            "trigger": trigger,
            "body": body.strip(),
            "path": str(path.absolute()),
        }

    def register_skills(self, tool_registry) -> List[SkillTool]:
        """将发现的 skills 注册到 ToolRegistry

        必须先调用 scan_skills() 发现 skill，否则注册列表为空。

        Args:
            tool_registry: hello-agents ToolRegistry 实例

        Returns:
            注册成功的 SkillTool 列表
        """
        self._tools = []

        for skill_meta in self._discovered:
            try:
                tool = SkillTool(
                    name=skill_meta["name"],
                    description=skill_meta["description"],
                    trigger=skill_meta["trigger"],
                    body=skill_meta["body"],
                    skill_path=skill_meta["path"],
                )
                tool_registry.register_tool(tool)
                self._tools.append(tool)
                logger.info(f"注册 Skill Tool: {tool.name}")
            except Exception as e:
                logger.error(
                    f"注册 Skill 失败: {skill_meta.get('name', '?')} - {e}"
                )

        logger.info(f"成功注册 {len(self._tools)} 个 Skill Tool")
        return self._tools

    def watch(self, callback: Optional[Callable] = None, interval: float = 5.0):
        """监听 skills 目录的文件变化（基本实现）

        使用轮询方式检测 SKILL.md 文件变化，变化时触发回调。

        Args:
            callback: 变化回调函数，签名 callback(changed_files: List[str])
            interval: 轮询间隔（秒），默认 5 秒

        注意:
            这是一个基础实现，适合开发环境。
            生产环境建议使用 watchdog 等库实现真正的文件系统监听。
        """
        import threading

        self._watching = True
        file_mtimes: Dict[str, float] = {}

        def _get_skill_files() -> Dict[str, float]:
            """获取所有 SKILL.md 文件及其修改时间"""
            result = {}
            if self.skills_dir.exists():
                for f in self.skills_dir.rglob("SKILL.md"):
                    result[str(f)] = f.stat().st_mtime
            return result

        def _watch_loop():
            nonlocal file_mtimes
            file_mtimes = _get_skill_files()

            while self._watching:
                time.sleep(interval)
                current_files = _get_skill_files()

                # 检测新增和修改的文件
                changed = []
                for fpath, mtime in current_files.items():
                    if fpath not in file_mtimes or file_mtimes[fpath] != mtime:
                        changed.append(fpath)

                # 检测删除的文件
                for fpath in file_mtimes:
                    if fpath not in current_files:
                        changed.append(fpath)

                if changed and callback:
                    try:
                        callback(changed)
                    except Exception as e:
                        logger.error(f"Watch 回调执行失败: {e}")

                file_mtimes = current_files

        self._watch_thread = threading.Thread(
            target=_watch_loop, daemon=True, name="skill-watch"
        )
        self._watch_thread.start()
        logger.info(f"开始监听 Skill 目录: {self.skills_dir} (间隔 {interval}s)")

    def stop_watch(self):
        """停止文件监听"""
        self._watching = False
        if self._watch_thread and self._watch_thread.is_alive():
            self._watch_thread.join(timeout=2)
        logger.info("Skill 文件监听已停止")

    @property
    def discovered_skills(self) -> List[Dict[str, Any]]:
        """获取已发现的 skill 列表"""
        return self._discovered

    @property
    def registered_tools(self) -> List[SkillTool]:
        """获取已注册的 SkillTool 列表"""
        return self._tools

    # ---- 内部方法 ----

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple:
        """解析 Markdown 文件的 YAML frontmatter

        Returns:
            (frontmatter_dict, body) 元组
            如果没有 frontmatter，frontmatter_dict 为空 dict
        """
        # 匹配 --- ... --- 块
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not match:
            return {}, content

        yaml_str = match.group(1)
        body = match.group(2)

        # 简易 YAML 解析（避免引入 pyyaml 依赖）
        frontmatter = {}
        current_key = None
        current_value_lines = []

        for line in yaml_str.split("\n"):
            # 跳过空行
            if not line.strip():
                continue

            # 检查是否是新的 key: value 行
            key_match = re.match(r"^(\w[\w_-]*):\s*(.*)$", line)
            if key_match:
                # 保存上一个 key
                if current_key:
                    frontmatter[current_key] = "\n".join(current_value_lines).strip()
                current_key = key_match.group(1)
                current_value_lines = [key_match.group(2)]
            else:
                # 继续上一个 key 的值（多行值）
                current_value_lines.append(line)

        # 保存最后一个 key
        if current_key:
            frontmatter[current_key] = "\n".join(current_value_lines).strip()

        return frontmatter, body
