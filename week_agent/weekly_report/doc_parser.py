"""Word 文档解析器 - 用 python-docx 提取上传 Word 的纯文本"""

from pathlib import Path

from docx import Document


def parse_docx_to_text(file_path: Path) -> str:
    """解析 .docx 文件为纯文本

    提取段落 + 表格内容，按顺序拼接。

    Args:
        file_path: .docx 文件路径

    Returns:
        纯文本内容

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件解析失败
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Word 文件不存在: {file_path}")

    try:
        doc = Document(str(file_path))
    except Exception as e:
        raise ValueError(f"Word 文件解析失败: {e}")

    parts: list[str] = []

    # 段落
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    # 表格
    for table in doc.tables:
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells]
            line = " | ".join(row_cells)
            if line.strip():
                parts.append(line)

    return "\n".join(parts)
