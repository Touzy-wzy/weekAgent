# -*- coding: utf-8 -*-
"""日志监控工具集（hello-agents Tool）

借鉴 QwenPaw 的实现方式：Agent 通过工具访问外部能力，这里把"读取并提取
日志文件中的异常记录"封装为一个 hello-agents Tool，注册到 ReActAgent 后由
LLM 自主决策调用。
"""

from pathlib import Path
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

from . import config
from .log_parser import extract_watch_records


class LogReadTool(Tool):
    """读取日志文件并提取 WARNING / ERROR 级别的异常记录

    供 LLM 使用：传入文件路径（可选，默认全部监控文件），返回该文件中
    WARNING/ERROR 级别的记录文本，供语义分析判断异常。
    """

    def __init__(self):
        super().__init__(
            name="log_read_anomalies",
            description=(
                "读取本地日志文件，并提取其中 WARNING 和 ERROR 级别的异常记录。"
                "返回每条记录的时间戳、级别、模块和消息正文（自动聚合多行续行、"
                "自动规避超长消息）。用于日志异常分析与告警判断。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filepath",
                type="string",
                description=(
                    "可选的日志文件路径。不填则读取全部默认监控文件。"
                    "可用 ; 分隔多个文件。"
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="max_records",
                type="integer",
                description="每个文件最多返回的异常记录条数（默认 60，取最新）",
                required=False,
                default=config.MAX_ANALYZE_RECORDS,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        filepath = str(parameters.get("filepath") or "").strip()
        max_records = int(parameters.get("max_records") or config.MAX_ANALYZE_RECORDS)

        # 解析文件列表
        if filepath and ";" in filepath:
            files = [f.strip() for f in filepath.split(";") if f.strip()]
        elif filepath:
            files = [filepath]
        else:
            files = list(config.LOG_FILES)

        print(f"📄 [log_read_anomalies] files={files} max={max_records}")
        try:
            sections: list[str] = []
            total = 0
            for fp in files:
                path = Path(fp)
                if not path.exists():
                    sections.append(f"[缺失] {fp}：文件不存在")
                    continue
                recs = extract_watch_records(fp, max_records=max_records)
                total += len(recs)
                if not recs:
                    sections.append(f"[{fp}] 无 WARNING/ERROR 记录")
                    continue
                body = "\n".join(r.truncated for r in recs)
                sections.append(f"===== {fp}（{len(recs)} 条）=====\n{body}")

            text = "\n\n".join(sections)
            if not text:
                text = "未读取到任何异常日志记录。"
            text = f"共提取 {total} 条 WARNING/ERROR 异常记录：\n\n{text}"

            print(f"  ✅ 提取 {total} 条异常记录")
            # 附一行位置索引，便于 LLM / 调试定位（不混入正文）
            pos_lines = []
            for fp in files:
                path = Path(fp)
                if not path.exists():
                    continue
                recs = extract_watch_records(fp, max_records=max_records)
                for r in recs:
                    span = (
                        f"{r.start_line}"
                        if r.start_line == r.end_line
                        else f"{r.start_line}-{r.end_line}"
                    )
                    pos_lines.append(f"    {Path(fp).name}: 行 {span} | {r.level} | {r.module}")
            if pos_lines:
                print("[位置索引]")
                print("\n".join(pos_lines))
            return ToolResponse.success(
                text=text,
                data={"files": files, "total_records": total},
            )
        except Exception as e:
            print(f"  ❌ 读取日志失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"读取日志失败: {str(e)}",
                context={"filepath": filepath, "files": files},
            )


class LogListFilesTool(Tool):
    """列出当前可用的日志文件（不读取内容，只展示文件信息）

    供 LLM 在读取前先"看到"目录里有什么文件，再决定读哪个。
    支持 glob 模式过滤。
    """

    def __init__(self):
        super().__init__(
            name="log_list_files",
            description=(
                "列出当前可用的日志文件（不读取内容）。"
                "返回文件名、大小、修改时间，供决定读取哪些文件。"
                "支持自定义 glob 模式过滤。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="glob_pattern",
                type="string",
                description=(
                    "自定义 glob 模式（可选）。"
                    "默认扫描 *.log，传 'app.log*' 可只看 app 相关日志。"
                ),
                required=False,
                default="",
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        glob_pattern = str(parameters.get("glob_pattern") or "").strip() or None

        print(f"📂 [log_list_files] glob={glob_pattern or config.LOG_MONITOR_GLOB}")

        try:
            text = config.list_log_files_as_text(glob_pattern=glob_pattern)
            files = config.resolve_log_files(glob_pattern=glob_pattern)

            print(f"  ✅ 发现 {len(files)} 个文件")

            return ToolResponse.success(
                text=text,
                data={"files": [str(f) for f in files], "count": len(files)},
            )
        except Exception as e:
            print(f"  ❌ 列出文件失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"列出日志文件失败: {str(e)}",
            )