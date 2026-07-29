"""FlowUsAgent - ReActAgent 子类，注入历史消息 + 修复 TraceLogger 句柄

核心改进：
1. 重写 _build_messages：把 history_manager 中的历史真正发给 LLM
   （hello-agents 原版只记录历史不发送，导致"说一句忘一句"）
2. 重写 run：每次执行后重新初始化 trace_logger，避免文件句柄关闭报错
   （原版 finalize() 后再 run() 会报 "I/O operation on closed file"）
3. 重写 _generate_smart_summary：摘要 LLM 复用主 LLM 配置
   （原版默认用 deepseek-chat，我们环境是 modelscope）
"""

from datetime import datetime
from typing import Any, Dict, List

from hello_agents.agents.react_agent import ReActAgent
from hello_agents.core.agent import Agent
from hello_agents.core.config import Config
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.message import Message
from hello_agents.observability.trace_logger import TraceLogger


class FlowUsAgent(ReActAgent):
    """支持多轮对话记忆的 FlowUs Agent"""

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        tool_registry=None,
        system_prompt: str | None = None,
        config: Config | None = None,
        max_steps: int = 6,
    ):
        super().__init__(
            name=name,
            llm=llm,
            tool_registry=tool_registry,
            system_prompt=system_prompt,
            config=config,
            max_steps=max_steps,
        )

        # 缓存主 LLM 配置，供智能摘要复用
        self._main_llm = llm

    # ------------------------------------------------------------------
    # 关键改进 1：注入历史消息
    # ------------------------------------------------------------------
    def _build_messages(self, input_text: str) -> List[Dict[str, str]]:
        """构建消息列表，注入历史对话（原版缺失的关键步骤）

        结构：system + 历史消息 + 当前用户问题
        """
        messages: List[Dict[str, str]] = []

        # 1. 系统提示词
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 2. 注入历史消息（来自 history_manager）
        #    hello-agents 原版 _build_messages 完全忽略 history_manager，
        #    导致 LLM 看不到之前的对话。
        history = self.get_history()
        if history:
            for msg in history:
                # 跳过 summary 占位消息中的系统标记，保留 content
                role = msg.role if msg.role in ("user", "assistant", "system") else "user"
                messages.append({"role": role, "content": msg.content})

        # 3. 当前用户问题
        messages.append({"role": "user", "content": input_text})

        return messages

    # ------------------------------------------------------------------
    # 关键改进 2：修复 TraceLogger 文件句柄
    # ------------------------------------------------------------------
    def run(self, input_text: str, **kwargs) -> str:
        """运行 Agent，每次执行前重置 trace_logger

        原版 run() 结束时调用 trace_logger.finalize() 关闭文件，
        同一实例再次 run() 会报 "I/O operation on closed file"。
        这里在每次 run() 开始时重新初始化 trace_logger。
        """
        # 如果 trace_logger 已存在且文件已关闭，重新初始化
        if self.trace_logger and self._is_trace_closed():
            self._reset_trace_logger()

        return super().run(input_text, **kwargs)

    def _is_trace_closed(self) -> bool:
        """检查 trace_logger 的文件句柄是否已关闭"""
        try:
            return self.trace_logger.jsonl_file.closed
        except (AttributeError, Exception):
            return False

    def _reset_trace_logger(self):
        """重新初始化 trace_logger（创建新的文件句柄）"""
        try:
            # 读取原配置
            output_dir = str(self.trace_logger.output_dir)
            sanitize = self.trace_logger.sanitize
            html_include_raw = self.trace_logger.html_include_raw

            # 创建新的 TraceLogger 实例
            self.trace_logger = TraceLogger(
                output_dir=output_dir,
                sanitize=sanitize,
                html_include_raw_response=html_include_raw,
            )
        except Exception as e:
            print(f"⚠️ TraceLogger 重置失败: {e}，关闭 trace")
            self.trace_logger = None

    # ------------------------------------------------------------------
    # 关键改进 3：智能摘要复用主 LLM
    # ------------------------------------------------------------------
    def _generate_smart_summary(self, history: List[Message]) -> str:
        """生成智能摘要，复用主 LLM 而非默认的 deepseek-chat

        原版 _get_summary_llm() 用 config.summary_llm_provider + model，
        默认是 deepseek/deepseek-chat，我们环境没有这个 provider。
        这里直接用主 LLM 生成摘要。
        """
        from hello_agents.core.message_history import HistoryManager

        # 1. 提取要压缩的历史片段（保留最近 N 轮）
        boundaries = self.history_manager.find_round_boundaries()
        if len(boundaries) <= self.config.min_retain_rounds:
            return self._generate_simple_summary(history)

        keep_from_index = boundaries[-self.config.min_retain_rounds]
        to_compress = history[:keep_from_index]

        if not to_compress:
            return self._generate_simple_summary(history)

        # 2. 构建摘要 Prompt
        history_text = self._format_history_for_summary(to_compress)

        summary_prompt = f"""请将以下对话历史压缩为结构化摘要，保留关键信息：

## 对话历史
{history_text}

## 摘要要求
1. **任务目标**：用户想要完成什么？
2. **关键决策**：做了哪些重要决定？
3. **已完成工作**：完成了哪些任务？（列表形式）
4. **待处理事项**：还有什么未完成？
5. **重要发现**：有哪些关键信息或问题？

请用简洁的中文输出，每部分不超过 3 行。"""

        # 3. 调用主 LLM 生成摘要
        try:
            messages = [
                {"role": "system", "content": "你是一个专业的对话摘要助手，擅长提取关键信息。"},
                {"role": "user", "content": summary_prompt},
            ]

            # 直接用主 LLM（绕过 _get_summary_llm 的 deepseek 默认配置）
            response = self._main_llm.invoke(
                messages,
                temperature=self.config.summary_temperature,
                max_tokens=self.config.summary_max_tokens,
            )

            # HelloAgentsLLM.invoke 返回 LLMResponse 对象，content 是文本
            summary_text = response.content if hasattr(response, "content") else str(response)

            return f"""## 历史摘要（{len(to_compress)} 条消息）
{summary_text}

---
（已压缩，保留最近 {self.config.min_retain_rounds} 轮完整对话）"""

        except Exception as e:
            print(f"⚠️ 智能摘要生成失败: {e}，使用简单摘要")
            return self._generate_simple_summary(history)
