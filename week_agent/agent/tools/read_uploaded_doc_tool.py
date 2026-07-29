"""读取上传 Word 文件工具"""

from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

from week_agent.config import DATA_DIR
from week_agent.weekly_report.doc_parser import parse_docx_to_text


class ReadUploadedDocTool(Tool):
    """读取已上传到会话的 Word 文件，返回纯文本"""

    def __init__(self):
        super().__init__(
            name="read_uploaded_doc",
            description=(
                "读取指定会话已上传的 Word 文件，返回纯文本内容。"
                "用于周报数据源 B：从用户上传的 .docx 解析素材。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="session_id",
                type="string",
                description="周报会话 ID（上传文件时绑定的 session_id）",
                required=True,
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        session_id = parameters.get("session_id", "").strip()
        if not session_id:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="session_id 不能为空",
            )

        # 在 data/uploads/{session_id}/ 下查找 .docx
        upload_dir = DATA_DIR / "uploads" / session_id
        if not upload_dir.exists():
            return ToolResponse.error(
                code=ToolErrorCode.NOT_FOUND,
                message=f"会话 {session_id} 未上传任何文件",
            )

        # 取第一个 .docx 文件
        docx_files = list(upload_dir.glob("*.docx"))
        if not docx_files:
            return ToolResponse.error(
                code=ToolErrorCode.NOT_FOUND,
                message=f"会话 {session_id} 上传目录无 .docx 文件",
            )

        file_path = docx_files[0]
        print(f"📄 [read_uploaded_doc] 读取: {file_path.name}")
        try:
            text = parse_docx_to_text(file_path)
            if not text:
                return ToolResponse.partial(
                    text=f"文件 {file_path.name} 内容为空",
                    data={"session_id": session_id, "file": file_path.name, "text": ""},
                )
            print(f"  ✅ 解析成功，{len(text)} 字符")
            return ToolResponse.success(
                text=f"Word 文件 {file_path.name} 解析成功（{len(text)} 字符）：\n\n{text[:6000]}",
                data={
                    "session_id": session_id,
                    "file": file_path.name,
                    "text": text,
                    "length": len(text),
                },
            )
        except Exception as e:
            print(f"  ❌ 解析失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"Word 文件解析失败: {str(e)}",
                context={"session_id": session_id, "file": file_path.name},
            )
