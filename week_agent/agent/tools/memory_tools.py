"""MemorySearchTool - 语义搜索长期记忆文件

扫描 MEMORY.md 和 memory/*.md 文件，按 heading / 段落切分后，
用 BM25-like 评分对每个 chunk 打分，返回 top 结果（含文件路径、行号、分数）。

不依赖任何外部向量数据库，纯 Python 实现。
"""

import glob
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse


# ---------------------------------------------------------------------------
# BM25 参数
# ---------------------------------------------------------------------------

BM25_K1 = 1.5   # 词频饱和参数
BM25_B = 0.75   # 文档长度归一化参数


# ---------------------------------------------------------------------------
# 辅助：把文件内容按 heading 或空行切分成 chunks
# ---------------------------------------------------------------------------

def _split_chunks(filepath: str) -> List[Dict[str, Any]]:
    """将 markdown 文件切分为语义块。

    切分规则：
    1. 遇到 heading（# 开头的行）时开新块
    2. 遇到连续两个空行时开新块
    3. 每个块记录起始行号（1-based）和文本内容

    Returns:
        [{"text": str, "start_line": int, "file": str}, ...]
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    chunks: List[Dict[str, Any]] = []
    current_lines: List[str] = []
    current_start = 1
    blank_count = 0

    for i, line in enumerate(lines, 1):
        is_heading = bool(re.match(r"^#{1,6}\s", line))
        is_blank = line.strip() == ""

        if is_heading and current_lines:
            # 开新块
            chunks.append({
                "text": "".join(current_lines).strip(),
                "start_line": current_start,
                "file": filepath,
            })
            current_lines = []
            current_start = i
            blank_count = 0

        if is_blank:
            blank_count += 1
            if blank_count >= 2 and current_lines:
                # 连续两个空行 → 开新块
                chunks.append({
                    "text": "".join(current_lines).strip(),
                    "start_line": current_start,
                    "file": filepath,
                })
                current_lines = []
                current_start = i + 1
                blank_count = 0
        else:
            blank_count = 0

        current_lines.append(line)

    # 最后一块
    if current_lines:
        text = "".join(current_lines).strip()
        if text:
            chunks.append({
                "text": text,
                "start_line": current_start,
                "file": filepath,
            })

    return chunks


# ---------------------------------------------------------------------------
# 简单中文分词（基于字符 n-gram + 常用停用词过滤）
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    # 常见中文停用词 + 英文停用词
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "们", "那", "些", "什么", "怎么", "这个", "那个", "可以",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "and",
    "but", "or", "not", "so", "if", "it", "its", "this", "that",
    "these", "those", "i", "you", "he", "she", "we", "they",
})


def _tokenize(text: str) -> List[str]:
    """将文本切分为 token 列表。

    策略：
    - 英文按空格/标点分词，转小写
    - 中文按 unigram + bigram 切分（简单但对短文本有效）
    - 过滤停用词和单字符
    """
    tokens: List[str] = []

    # 先提取英文单词
    eng_words = re.findall(r"[a-zA-Z_]{2,}", text.lower())
    for w in eng_words:
        if w not in _STOP_WORDS:
            tokens.append(w)

    # 中文字符提取
    cn_chars = re.findall(r"[\u4e00-\u9fff]", text)

    # unigram
    for ch in cn_chars:
        if ch not in _STOP_WORDS:
            tokens.append(ch)

    # bigram
    for i in range(len(cn_chars) - 1):
        bigram = cn_chars[i] + cn_chars[i + 1]
        if bigram not in _STOP_WORDS:
            tokens.append(bigram)

    return tokens


# ---------------------------------------------------------------------------
# BM25-like 评分
# ---------------------------------------------------------------------------

def _bm25_score(
    query_tokens: List[str],
    chunk_tokens: List[str],
    chunk_length: int,
    avg_chunk_length: float,
    doc_freq: Dict[str, int],
    total_docs: int,
) -> float:
    """计算单个 chunk 的 BM25-like 分数。

    Args:
        query_tokens: 查询词列表
        chunk_tokens: 当前 chunk 的 token 列表
        chunk_length: 当前 chunk 的 token 数
        avg_chunk_length: 所有 chunk 的平均 token 数
        doc_freq: 每个 term 出现在多少个 chunk 中
        total_docs: 总 chunk 数

    Returns:
        BM25 分数（float >= 0）
    """
    if not query_tokens or chunk_length == 0:
        return 0.0

    # 统计当前 chunk 中每个 term 的词频
    tf_map: Dict[str, int] = {}
    for t in chunk_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1

    score = 0.0
    for term in query_tokens:
        if term not in tf_map:
            continue

        tf = tf_map[term]
        df = doc_freq.get(term, 0)

        # IDF: log((N - df + 0.5) / (df + 0.5))
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1e-10)

        # TF 归一化
        tf_norm = (tf * (BM25_K1 + 1)) / (
            tf + BM25_K1 * (1 - BM25_B + BM25_B * chunk_length / avg_chunk_length)
        )

        score += idf * tf_norm

    return score


# ---------------------------------------------------------------------------
# Tool 类
# ---------------------------------------------------------------------------

class MemorySearchTool(Tool):
    """语义搜索长期记忆文件（MEMORY.md 和 memory/*.md）"""

    def __init__(self, memory_root: Optional[str] = None):
        """
        Args:
            memory_root: 记忆文件的根目录。默认使用当前工作目录。
        """
        super().__init__(
            name="memory_search",
            description="语义搜索长期记忆文件",
        )
        self._memory_root = memory_root or os.getcwd()

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="搜索关键词",
                required=True,
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="最大返回结果数（默认 5）",
                required=False,
                default=5,
            ),
            ToolParameter(
                name="min_score",
                type="number",
                description="最小相关性分数（默认 0）",
                required=False,
                default=0.0,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        query = parameters.get("query", "").strip()
        if not query:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="query 不能为空",
            )

        max_results = parameters.get("max_results", 5)
        min_score = parameters.get("min_score", 0.0)

        print(f"🧠 [memory_search] query='{query}' max={max_results} min_score={min_score}")

        try:
            results = self._search(query, max_results, min_score)

            if not results:
                return ToolResponse.partial(
                    text=f"未找到与 '{query}' 相关的记忆片段",
                    data={"query": query, "results": []},
                )

            # 构建人类可读的文本输出
            text_lines = [f"搜索 '{query}' 共找到 {len(results)} 条相关记忆："]
            for i, r in enumerate(results, 1):
                rel_path = os.path.relpath(r["file"], self._memory_root)
                text_lines.append(
                    f"{i}. [{r['score']:.3f}] {rel_path}:{r['start_line']}"
                )
                # 截断展示文本
                preview = r["text"][:300]
                if len(r["text"]) > 300:
                    preview += "..."
                text_lines.append(f"   {preview}")
            text = "\n".join(text_lines)

            print(f"  ✅ 找到 {len(results)} 条结果")
            return ToolResponse.success(
                text=text,
                data={"query": query, "results": results},
            )

        except Exception as e:
            print(f"  ❌ 搜索记忆失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"搜索记忆失败: {str(e)}",
                context={"query": query},
            )

    def _search(
        self, query: str, max_results: int, min_score: float
    ) -> List[Dict[str, Any]]:
        """执行 BM25 搜索，返回 top 结果列表。"""
        # 1. 收集所有记忆文件
        files = self._collect_memory_files()
        if not files:
            return []

        # 2. 切分所有文件为 chunks
        all_chunks: List[Dict[str, Any]] = []
        for fp in files:
            all_chunks.extend(_split_chunks(fp))

        if not all_chunks:
            return []

        # 3. 计算文档频率（每个 term 出现在多少个 chunk 中）
        total_docs = len(all_chunks)
        doc_freq: Dict[str, int] = {}
        chunk_token_lists: List[List[str]] = []

        for chunk in all_chunks:
            tokens = _tokenize(chunk["text"])
            chunk_token_lists.append(tokens)
            seen = set(tokens)
            for t in seen:
                doc_freq[t] = doc_freq.get(t, 0) + 1

        # 4. 计算平均 chunk 长度
        lengths = [len(toks) for toks in chunk_token_lists]
        avg_length = sum(lengths) / len(lengths) if lengths else 1.0

        # 5. 对每个 chunk 计算 BM25 分数
        query_tokens = _tokenize(query)
        scored: List[Tuple[float, int]] = []
        for i, tokens in enumerate(chunk_token_lists):
            score = _bm25_score(
                query_tokens, tokens, lengths[i],
                avg_length, doc_freq, total_docs,
            )
            if score > min_score:
                scored.append((score, i))

        # 6. 排序并返回 top N
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_results]

        results: List[Dict[str, Any]] = []
        for score, idx in top:
            chunk = all_chunks[idx]
            results.append({
                "text": chunk["text"],
                "file": chunk["file"],
                "start_line": chunk["start_line"],
                "score": round(score, 4),
            })

        return results

    def _collect_memory_files(self) -> List[str]:
        """收集 MEMORY.md 和 memory/*.md 文件列表。

        搜索路径：
        1. {memory_root}/MEMORY.md
        2. {memory_root}/memory/*.md
        """
        root = self._memory_root
        files: List[str] = []

        # MEMORY.md
        memory_md = os.path.join(root, "MEMORY.md")
        if os.path.isfile(memory_md):
            files.append(memory_md)

        # memory/*.md
        memory_dir = os.path.join(root, "memory")
        if os.path.isdir(memory_dir):
            pattern = os.path.join(memory_dir, "*.md")
            files.extend(sorted(glob.glob(pattern)))

        return files
