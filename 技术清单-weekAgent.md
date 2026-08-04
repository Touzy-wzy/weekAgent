# weekAgent 技术文档

> 基于项目源码分析，覆盖提示词、历史消息、上下文管理、输出控制、记忆、MCP、Skills、外部交互八大模块。
> 项目基于开源框架 **hello-agents 1.0.0** 二次开发，包含两套子智能体：周报智能体（FlowUs + Excel + 邮件）与日志监控智能体。
> 已集成 **SQLiteHistoryStore** 实现持久化多会话历史管理，修复 Message 对象兼容性问题，支持调试模式交互式对话。

---

## 一、提示词的内容（Prompt）

项目中存在 **4 套系统提示词**，均采用**模板化 + 动态注入**架构：提示词只保留行为指导，工具描述通过 `tool_descriptions.build_tool_summary()` 在运行时从 `ToolRegistry` 的 JSON Schema 动态生成，与 function calling schema 保持**单一真相源**。

### 1. FlowUs 助手提示词 —— `week_agent/agent/prompts.py` 的 `FLOWUS_SYSTEM_PROMPT_TPL`

```
结构：{tool_summary} + 工作原则 + 对话原则
```

- **{tool_summary}**：运行时动态注入，由 `build_tool_summary(agent.get_tool_schemas())` 生成
- **工作原则（意图分流）**：看某项目全部内容 → 先 `list_pages` 再对相关页面 `get_page`；搜主题 → `search` 再 `get_page`；已知 page_id → 直接 `get_page`；主动取前 2–3 个相关页面；回答引用页面标题并给 page_id
- **对话原则（多轮记忆）**：强调"能看到之前的对话历史"；指代词（他/这个/上面那个/刚才）从历史找；不重复问、不重复调用已执行工具；"继续/详细说说"基于上次回答展开

### 2. 周报助手提示词 —— `week_agent/agent/prompts.py` 的 `WEEKLY_REPORT_PROMPT_TPL`

按 **5 个阶段** 驱动状态机式工作流：

1. **收集要素**：判断缺 `reporter_name` / `week_range` / `data_source`；flowus 还缺 `flowus_project`，docx 缺已上传文件；缺信息反问且"一次问清"
2. **拉取素材**：flowus 调 `flowus_fetch_weekly`（明确"不要自己组合 search+get"）；docx 调 `read_uploaded_doc`
3. **生成结构化数据**：给出周报 JSON schema 示例，**严格枚举约束**：`category∈{61850,AI,其他}`；本周 `status∈{已完成,进行中,已延期}`；下周 `status∈{完成,开展,延期}`；每数组最多 5 项
4. **填写 Excel**：调 `fill_weekly_excel`，告知已生成草稿待审核
5. **邮件发送**（须在审核通过 + 提供收件人后）：先 `agently_compose_mail` 展示 confirmation_token → 用户二次确认 → `agently_send_mail`

### 3. 日志分析提示词（批处理版） —— `week_agent/log_monitor/agent.py` 的 `LOG_AGENT_SYSTEM_PROMPT_TPL`

- **工具说明**：运行时动态注入
- **工作流程**：读取 → 语义分析（异常类型/严重级别 critical|warning|info/影响面/处置建议）→ 汇总
- **输出格式**（强约束结构化）：`【日志分析报告】` 模板，含"分析时间 / 共发现 N 个异常／── 异常 1 [级别]：现象/影响/建议／【告警建议】需要立即告警: 是/否"

### 4. 日志监控助手提示词（对话版） —— `week_agent/agent/log_monitor_agent.py` 的 `LOG_MONITOR_SYSTEM_PROMPT_TPL`

- **工具说明**：运行时动态注入（含新增的 `log_list_files`）
- **工作流程建议**：仅看分布 → `log_list_files` + `log_preview`；要语义分析 → `log_read_anomalies`；要完整监测 → `run_log_check`；要定位行号 → `log_position_lookup`
- **定时任务场景**：不传参数自动扫描所有日志文件

### 提示词架构的核心设计

```
┌─────────────────────────────────────────────┐
│  Tool 类 (name/description/parameters)      │  ← 唯一真相源
└─────────────────┬───────────────────────────┘
                  │ get_tool_schemas()
                  ▼
┌─────────────────────────────────────────────┐
│  build_tool_summary()                       │  ← 运行时动态生成
│  生成人类可读的工具摘要文本                    │
└─────────────────┬───────────────────────────┘
                  │ {tool_summary}
                  ▼
┌─────────────────────────────────────────────┐
│  系统提示词模板                               │  ← 只保留行为指导
│  FLOWUS_SYSTEM_PROMPT_TPL                   │
│  LOG_MONITOR_SYSTEM_PROMPT_TPL              │
└─────────────────────────────────────────────┘
```

**收益**：加减工具零提示词改动；工具描述永远一致；提示词省 token（不重复写参数说明）。

---

## 二、历史消息管理（History management）

项目把历史管理拆成三层，支持多会话、持久化与框架兼容：

### 1. 持久化存储层：`SQLiteHistoryStore`（新增）

`week_agent/memory/history_store.py`：基于 SQLite 的历史消息持久化存储，替代原版内存 `HistoryManager`。

**核心功能**：
- **多会话隔离**：`session_id` 分区存储，支持独立的会话历史管理
- **消息格式兼容**：`append()` 同时支持 **Message 对象**（hello-agents 框架传入）与**字典格式**（内部使用）
  ```python
  # Message 对象支持
  if hasattr(message, 'role'):  # Message 对象
      role = message.role
      content = message.content
  else:  # 字典格式
      role = message.get("role")
      content = message.get("content")
  ```
- **轮次识别**：`find_round_boundaries()` 返回每轮用户消息的索引（role='user'）
- **历史压缩**：`compress(summary)` 删除旧消息，插入一条摘要系统消息
- **序列化**：`to_dict()` / `load_from_dict()` 支持会话导入/导出
- **数据库**：SQLite 文件 `week_agent/memory/history.db`；内存模式支持测试（`:memory:`）

**关键改进（解决 Message 对象不兼容）**：
- 原版设计期望 `append()` 收到字典，但 hello-agents 框架的 `save_session()` 传入 Message 对象
- 修复后，`append()` 自动检测对象类型，统一转换为数据库行

### 2. Hello-agents 框架层：原版 `HistoryManager` 的替代

`FlowUsAgent` 初始化时用 `SQLiteHistoryStore` 覆盖 `history_manager`：

```python
self.history_manager = SQLiteHistoryStore(
    session_id=session_id,
    min_retain_rounds=config.min_retain_rounds if config else 10,
)
```

- 保留原版 API（`append` / `get_history` / `clear` / `compress` / `find_round_boundaries`）
- 新增 `to_dict()` / `load_from_dict()` 用于会话序列化

### 3. 项目改进：`FlowUsAgent._build_messages` + 缺失方法补全

**核心问题**：
1. hello-agents 原版 `_build_messages` **只记录历史不发送** → 触发"说一句忘一句"
2. 框架与项目的 Message 对象/字典转换不一致，导致 `save_session()` 时报 `'Message' object has no attribute 'get'`

**解决方案**：
- 重写 `_build_messages`，支持 Message 对象与字典两种格式：
  ```python
  for msg in self.get_history():
      if hasattr(msg, 'role'):  # Message 对象
          role = msg.role if msg.role in ("user", "assistant", "system") else "user"
          content = msg.content
      else:  # 字典格式
          role = msg.get("role", "user") if msg.get("role") in ("user", "assistant", "system") else "user"
          content = msg.get("content", "")
      messages.append({"role": role, "content": content})
  ```
- 补全 `get_history()` / `clear_history()` 方法，委托给 `history_manager`

### 4. Web 层实例池（按 session_id 复用，保持多轮记忆）

- `week_agent/web/services.py`：`_agent_pool: dict[str,Any]`，`get_or_create_agent(session_id)` 按 session_id 复用同一 FlowUsAgent → `history_manager` 累积历史
- 简单 LRU，超 `_MAX_AGENTS=20` 清最早会话
- 实例池是**内存字典**（服务重启即清空）；但单个会话的历史持久化到 SQLite

### 5. CLI 交互式调试：会话级单例

`week_agent/cli.py` 的 `run_agent_debug()` / `run_log_agent_debug()`：
- 整个交互复用同一 agent 实例
- `history` 通过 `SQLiteHistoryStore` 自动累积到 `history.db`
- 支持 `clear` 指令调用 `agent.clear_history()` 清空会话历史
- 调试结束时自动保存 trace 文件与会话状态

---

## 三、上下文管理（Context management）

### 1. 运行时配置（`week_agent/agent/runner.py` 的 `create_agent_config`）

针对 modelscope DeepSeek 调优：

```python
Config(
    context_window=32768,           # 实际可用上下文（默认 128000 太大）
    compression_threshold=0.7,      # 70% 触发压缩，避免太晚
    min_retain_rounds=6,            # 压缩后保留 6 轮完整对话
    enable_smart_compression=True,  # 启用智能摘要
    summary_max_tokens=800,
    summary_temperature=0.3,
    auto_save_enabled=False,        # 关自动保存，避免文件句柄问题
    trace_enabled=True,
)
```

### 2. 智能摘要（基于 GSSC 式压缩管线）

**项目覆盖 `FlowUsAgent._generate_smart_summary`**（关键改进）：

- 用 `find_round_boundaries()` 圈定要压缩的历史片段（保留最近 `min_retain_rounds` 轮）
- 摘要 LLM **用主 LLM 替代默认 deepseek-chat**（原版用 `deepseek/deepseek-chat`，本环境没有该 provider）
- 摘要 Prompt 固定 5 点：任务目标 / 关键决策 / 已完成工作（列表）/ 待处理事项 / 重要发现，每部分不超 3 行
- 包装为 `## 历史摘要（{N} 条消息）...---（已压缩，保留最近 {min_retain_rounds} 轮）`
- 失败回退 `_generate_simple_summary`

### 3. 工具输出截断/防爆要点

| 截断点 | 位置 | 阈值 |
|---|---|---|
| 单条日志记录进 LLM | `log_monitor/config.py` `MAX_RECORD_CHARS` | 2000 字符 |
| 单次进 LLM 的记录数 | 同上 `MAX_ANALYZE_RECORDS` | 60 条（保留最新） |
| FlowUs 页面 Markdown | `agent/tools/flowus_tools.py` | 2000 字符 + `...(共 N 字，已截断)` |
| FlowUs 周报素材单页/整包 | `agent/tools/flowus_weekly_tool.py` | 单页 3000 字符，整包 6000 字符 |
| 上传 Word 文本 | `agent/tools/read_uploaded_doc_tool.py` | 6000 字符 |
| 工具输出上限（框架默认） | `hello_agents/core/config.py` | `tool_output_max_lines=2000`、`tool_output_max_bytes=51200` |

### 4. 日志文件自动发现（新增）

`log_monitor/config.py` 支持 glob 模式自动发现日志文件：

```python
# 环境变量配置
LOG_MONITOR_GLOB = "app.log*;logs/*.log"  # 分号分隔多个 glob 模式
LOG_DIR = "/path/to/logs"                  # 扫描根目录

# 核心函数
resolve_log_files(glob_pattern, log_dir, max_files)  # 展开为实际文件列表
list_log_files_as_text(glob_pattern)                  # 格式化输出供 LLM 阅读
```

- 支持分号分隔多个 glob 模式
- 自动去重 + 按修改时间倒序（最新的在前）
- 过滤空文件和不存在的路径
- 向后兼容：`LOG_FILES` 列表由 `resolve_log_files()` 动态生成

---

## 四、输出控制与格式解析（Output control & format parsing）

### 1. 统一响应模型

所有工具返回 hello-agents 的 `ToolResponse`，状态分 `success` / `partial` / `error`；失败带 `ToolErrorCode`（`INVALID_PARAM` / `EXECUTION_ERROR` / `NOT_FOUND` 等）。

### 2. FlowUs 响应解析函数（`week_agent/flowus/utils.py`）

- `extract_content`：从 MCP `CallToolResult.content[].text` 取出并自动 `json.loads`
- `extract_tool_result`：从 HTTP JSON-RPC 响应 `result.content[0].text` 解析 JSON
- `extract_page_ids`：从 search / semanticSearch 结果提取 page_id
- `parse_page_links(md_text)`：正则解析 FlowUs 子页面链接
- `extract_block_title(block)`：按块类型提取 `rich_text` 标题

### 3. LLM 结构化输出校验（周报）

- `week_agent/weekly_report/templates.py`：定义 `WEEKLY_REPORT_SCHEMA`（三段 JSON object、枚举、每段数组上限 5、各段 required），并实现 `validate_weekly_data()`
- `week_agent/agent/tools/fill_excel_tool.py`：将表参 `report_data`（字符串化 JSON）`json.loads` → 补默认段 → `validate_weekly_data` 通过后才写盘

### 4. 日志告警输出格式化（`week_agent/log_monitor/alerter.py`）

- `format_alert_payload()` 统一构造 `{severity,title,summary,body,time}`
- `ConsoleChannel`：印 icon+标题+摘要+详情
- `MailChannel`：复用邮件工具 `send_mail`
- `WecomChannel`：拼 markdown `### icon 标题\n> 级别 | 时间\n> 摘要\n\n正文[:1280]`
- 报告落盘 `(reports/log_alert_<时间戳>.md`)：头部统计 + LLM 正文 + 尾部 `location_manifest()` 位置索引

### 5. 工具位置索引

`LogReadAnomaliesTool` 和 `LogReadTool` 在输出末尾附加位置索引：

```
[位置索引]
    app.log: 行 1234-1250 | ERROR | main.app
    app1.log: 行 567 | WARNING | service.worker
```

便于 LLM 和开发者快速定位源码。

---

## 五、记忆管理（Memory）

### 1. 业务会话状态机 `WeeklySession`（`week_agent/weekly_report/session.py`）

- **状态机**：`init → gathering → drafting → filling → reviewing → collecting_recipient → confirming_send → sent / failed`
- **字段即业务记忆**：`reporter_name` / `week_range` / `data_source` / `uploaded_docx_path` / `flowus_project` / `material_text` / `draft_data` / `draft_xlsx_path` / `recipients` / `confirmation_token` / `mail_sent` / `history`
- **JSON 落盘**：`data/sessions/<session_id>.json`；`save()/load()/list_all()/delete()`；`transition()` 每次流转写 `updated_at` 并持久化
- **关键**：`material_text`（已拉取素材）存进会话，避免跨轮重复拉取

### 2. 记忆修复：正则结构化字段提取（`week_agent/web/weekly_services.py`）

`_extract_and_update_fields()`：用正则从用户原始消息抽取：
- 填报人（"填报人X/我叫X/姓名X"）
- 周报区间（日期范围或"周报区间X"）
- 数据源（flowus|docx|word|上传）
- FlowUs 项目名（显式"项目X"，或剔除已知短语后剩下连续中文串）

注释明确指出这是"修复'说一句忘一句'的根因"：原版只把信息存进 history、从不填充 `reporter_name` 等字段。

### 3. SQLiteHistoryStore 的持久化设计

`week_agent/memory/history_store.py` 补充说明：
- **会话隔离**：多个 `session_id` 共存同一 SQLite 数据库，互不干扰
- **Message 对象兼容**：`append()` 自动检测 Message 对象和字典，统一转为行记录
- **查询优化**：按 session_id 索引，轻量快速
- **故障恢复**：同步模式（`:memory:` 测试 / 文件 DB 生产），事务提交保证
- **轮次识别**：保留 `find_round_boundaries()` 供压缩用

### 4. 上下文提示词注入

`_build_context_prompt()`：把 `【当前会话状态】【填报人】【周报区间】【数据源】【FlowUs项目】【已上传文件】【草稿 xlsx】【收件人】` 拼进每次 user prompt。

### 4. 上传文件收档

`save_upload_file()`：写入 `data/uploads/<session_id>/<安全文件名>`（`Path(filename).name` 防路径穿越），并把 `uploaded_docx_path` 与 `data_source=docx` 写回会话。

### 5. 推理轨迹（traces）

开关 `trace_enabled=True`，`memory/traces/trace-*.jsonl`。`FlowUsAgent` 重造 `run()` 每次执行前检查 trace 文件句柄、已关闭则初始化新的 `TraceLogger`，避免 `finalize` 后再 `run` 报 "I/O operation on closed file"。

---

## 六、MCP 实现

对同一 FlowUs MCP 服务器实现了 **两套同通道**：

### 1. 官方工具性通道 —— `week_agent/flowus/mcp_client.py`

- 使用 `mcp`（`requirements.txt`：`mcp>=1.28.0`）+ `streamablehttp_client` + `ClientSession` + OAuth
- 方法：`init_session(callback)`（`asyncio.Lock` 串行）、`list_tools()`、`call_tool()`、`fetch_and_save()`
- 用于一次性 CLI 拉取场景

### 2. 直连 HTTP/JSON-RPC —— `week_agent/flowus/http_client.py`

- 面向 Web/Agent 高频调用，不依赖回调
- `initialize` 用 `protocolVersion:"2025-06-18"`
- `tools/call` 方法，header 带 `Authorization: Bearer <token>` 与 `mcp-session-id`
- 单例 `get_http_client()`；token 从 `.flowus_token` 读取
- 实际调用的 MCP 工具名：`API-getMe` / `API-search` / `API-semanticSearch` / `API-getMarkdown` / `API-getBlockChildren`

### 3. OAuth 2.0 + PKCE（`week_agent/flowus/auth.py`）

- 用 `mcp.client.auth.oauth2` 实现 `OAuthClientProvider`
- 文件 Token 存储：`.flowus_token.json`，避免每次重授权
- 本地回调 server：`asyncio.start_server` 监听 `127.0.0.1`（尝试端口 18923/18924/18925/{0 随机}）

### 4. Async bridging 关键架构

`week_agent/agent/tools/flowus_tools.py` 的 `_run_async(coro)`：在 `ThreadPoolExecutor` 新线程中 `new_event_loop(); run_until_complete()`——避免同步 ReAct 直接 `asyncio.run()` 与 FastAPI 事件循环冲突。

---

## 七、Skills 实现

- **项目没有定义自定义 Skills**：`E:\weekAgent` 根目录不存在 `skills/` 目录
- 全部外部能力扩展都走 hello-agents **工具机制（`ToolRegistry`）**——即上文列出的工具
- 框架 `hello_agents/core/config.py` 有 Skills 配置（`skills_enabled=True`、`skills_dir="skills"`、`skills_auto_register=True`），但本项目未使用
- **如实结论**：本项目对"Skills"没有落地实现——外部能力的真实载体是 Tools（ToolRegistry）

### 工具清单（共 14 个）

| 工具名 | 所属模块 | 功能 |
|--------|----------|------|
| `flowus_list_pages` | FlowUs | 列出项目下所有子页面 |
| `flowus_get_page` | FlowUs | 获取页面详情（Markdown） |
| `flowus_search` | FlowUs | 语义搜索工作空间 |
| `flowus_fetch_weekly` | FlowUs | 一次性拉取周报素材 |
| `agently_compose_mail` | 邮件 | 草拟邮件（返回 confirmation_token） |
| `agently_send_mail` | 邮件 | 发送邮件（带 token 二次确认） |
| `fill_weekly_excel` | 周报 | 填写 Excel 模板 |
| `read_uploaded_doc` | 周报 | 解析上传的 Word 文档 |
| `recall_history` | 记忆 | **[新增]** 回溯对话历史 |
| `memory_search` | 记忆 | **[新增]** 搜索历史关键词 |
| `log_list_files` | 日志监控 | 列出可用日志文件 |
| `log_read_anomalies` | 日志监控 | 读取日志异常（支持 glob 自动发现） |
| `log_position_lookup` | 日志监控 | 定位日志在源文件的行号 |
| `run_log_check` | 日志监控 | 完整检查+告警+报告 |
| `log_preview` | 日志监控 | 快速预览（不调 LLM） |

---

## 八、与外部系统的交互

### 1. 外部系统一览

| 外部系统 | 协议/方式 | 实现文件 | 要点 |
|---|---|---|---|
| FlowUs MCP 服务器 | 官方 MCP stream + 直连 JSON-RPC | `flowus/mcp_client.py`、`http_client.py` | 首 OAuth PKCE，后续 Bearer token |
| LLM（DeepSeek-V4-Flash / ModelScope） | OpenAI 兼容 invoke（`HelloAgentsLLM`） | `agent/runner.py`、框架 `hello_agents/core/llm.py` | 失败重试、摘要复用主 LLM |
| 邮件（agently-cli） | `subprocess` 调用命令行 | `agent/tools/agently_mail_tools.py` | 全局 npm 安装，`shutil.which()` 解析 `.cmd` |
| 企业微信群机器人 | `httpx` POST webhook（markdown） | `log_monitor/alerter.py` `WecomChannel` | critical 实时；`errcode==0` 判成功 |
| 邮件告警 | 复用 `AgentlySendMailTool` | `alerter.py` `MailChannel` | 默认 daily 每天一封，marker 去重 |
| Web UI | FastAPI + Uvicorn，前端 `static/index.html` | `web/app.py`、`run.py --web` | REST + 文件上传/下载 |
| Excel 模板 | openpyxl（保留样式） | `weekly_report/excel_filler.py` | 固定版式填写 |
| Word 上传解析 | python-docx（段落+表格） | `weekly_report/doc_parser.py`、`read_uploaded_doc_tool.py` | |
| 浏览器 OAuth 授权 | `webbrowser.open` + 本地回调 HTTP server | `flowus/auth.py` | |

### 2. 邮件子进程健壮性

`_run_agently_send` 的关键设计：
- `--to` 为 stringArray，多个收件人需重复 `--to`
- body 用 `--body-file`（临时目录相对路径），避免过长/换行/特殊字符破坏命令解析
- 附件复制到临时目录用相对文件名；中文名不被认时降级英文名 `weekly_report.xlsx` 重试
- 通过 CWD 切换保证相对路径解析；成功/异常路径清理临时目录；超时 60s

### 3. 统一入口与入口分层

`run.py` 提供多模式：

```
python run.py                     # CLI 拉取
python run.py --web               # Web UI
python run.py --agent "查询"       # 单次查询
python run.py --agent-debug       # 交互式 REPL
python run.py --log-agent "分析"   # 日志单次
python run.py --log-agent-debug    # 日志 REPL
python run.py --list-tools         # 列出工具
python run.py --max-steps 10       # 自定义步数
```

### 4. Web API 架构

- `week_agent/web/app.py`：FastAPI 路由，REST + 文件上传/下载
- `week_agent/web/services.py`：数据获取统一收敛到 Agent 工具层，Web UI 与 Agent 对话访问同一套工具连接层
- `ThreadPoolExecutor` 避免在异步路由中直接跑同步工具

---

## 九、最近修复：Message 对象兼容性与缺失方法

### 问题背景

在日志监控 Agent 调试模式（`run_log_agent_debug()`）中，Agent 执行查询后会自动保存会话。保存过程中，hello-agents 框架的 `save_session()` 会调用 `history_manager.append(message)`，传入的是 **Message 对象**。但当时 `SQLiteHistoryStore.append()` 期望字典格式，直接调用 `.get()` 方法，导致：

```
AttributeError: 'Message' object has no attribute 'get'
```

同时，`_build_messages()` 在处理历史时也没有区分两种格式，`FlowUsAgent` 中也缺少 `get_history()` 和 `clear_history()` 方法，导致调试模式无法清空历史。

### 修复方案

#### 1. **SQLiteHistoryStore.append() —— 双格式适配**

```python
def append(self, message: dict, session_id: str = None) -> None:
    # 支持 Message 对象和字典两种格式
    if hasattr(message, 'role'):  # Message 对象
        role = message.role
        content = message.content
        timestamp = getattr(message, 'timestamp', None)
        metadata = getattr(message, 'metadata', None)
    else:  # 字典格式
        role = message.get("role")
        content = message.get("content")
        timestamp = message.get("timestamp")
        metadata = message.get("metadata")
    
    metadata_str = json.dumps(metadata) if metadata else None
    # ... 数据库插入逻辑
```

#### 2. **FlowUsAgent._build_messages() —— 双格式处理**

```python
for msg in self.get_history():
    # 支持 Message 对象和字典两种格式
    if hasattr(msg, 'role'):  # Message 对象
        role = msg.role if msg.role in ("user", "assistant", "system") else "user"
        content = msg.content
    else:  # 字典格式
        role = msg.get("role", "user") if msg.get("role") in ("user", "assistant", "system") else "user"
        content = msg.get("content", "")
    messages.append({"role": role, "content": content})
```

#### 3. **FlowUsAgent —— 补全缺失方法**

```python
def get_history(self) -> List[Any]:
    """获取会话历史消息，兼容 hello-agents 框架"""
    if hasattr(self.history_manager, 'get_history'):
        return self.history_manager.get_history()
    elif hasattr(self.history_manager, 'messages'):
        return self.history_manager.messages
    return []

def clear_history(self) -> None:
    """清除会话历史消息"""
    if hasattr(self.history_manager, 'clear'):
        self.history_manager.clear()
    elif hasattr(self.history_manager, 'messages'):
        self.history_manager.messages = []
```

### 验证

修复后，日志监控调试模式运行正常，无错误报告：

```bash
PYTHONIOENCODING=utf-8 python run.py --log-agent-debug
# >>> 现在有几个日志文件
# [Agent 成功执行查询，返回结果]
# ✅ Trace 已保存
# [无异常] 会话成功保存
```



1. **多轮对话记忆 + SQLite 持久化**：用 `SQLiteHistoryStore` 替代内存 `HistoryManager`，支持多会话、持久化与框架 Message 对象兼容
2. **Message 对象适配器模式**：`SQLiteHistoryStore.append()` 和 `_build_messages()` 同时支持 Message 对象和字典格式，解决框架传入类型不一致问题
3. **工具单一真相源**：工具描述从 `Tool` 类动态生成，提示词只保留行为指导
4. **智能上下文压缩**：超过 70% 上下文窗口时触发摘要，保留最近 6 轮完整对话
5. **日志文件自动发现**：支持 glob 模式 + 按修改时间排序，适用于实时日志和定时任务
6. **邮件发送可靠性**：附件与 body 走临时文件 `--body-file` 与相对路径，两阶段确认
7. **TraceLogger 自动修复**：每次 `run()` 前检查文件句柄，避免 "I/O operation on closed file"
8. **会话状态保持**：Web 层按 `session_id` 维护 Agent 实例池并复用；CLI 调试模式用单例 Agent
9. **缺失方法补全**：在 `FlowUsAgent` 中补全 `get_history()` / `clear_history()` 方法，确保框架兼容性

---

## 附：文件结构概览

```
week_agent/
├── agent/
│   ├── flowus_agent.py          # FlowUsAgent（核心：历史注入 + TraceLogger 修复 + 智能摘要 + 缺失方法补全）
│   ├── log_monitor_agent.py     # LogMonitorAgent（日志监控智能体）
│   ├── prompts.py               # 提示词模板（动态注入工具描述）
│   ├── runner.py                # Agent 创建器（FlowUs + 日志监控）
│   ├── tool_descriptions.py     # 工具摘要生成器（单一真相源）
│   └── tools/
│       ├── __init__.py
│       ├── flowus_tools.py      # FlowUs 工具（list_pages/get_page/search）
│       ├── flowus_weekly_tool.py # 周报素材拉取
│       ├── agently_mail_tools.py # 邮件工具（compose/send）
│       ├── fill_excel_tool.py   # Excel 填写
│       ├── read_uploaded_doc_tool.py # Word 解析
│       ├── log_monitor_tools.py # 日志监控工具（5 个）
│       ├── history_tools.py     # 历史回溯工具
│       └── memory_tools.py      # 记忆搜索工具
├── flowus/
│   ├── auth.py                  # OAuth 2.0 + PKCE
│   ├── http_client.py           # 直连 HTTP/JSON-RPC
│   ├── mcp_client.py            # 官方 MCP 通道
│   └── utils.py                 # 响应解析函数
├── log_monitor/
│   ├── config.py                # 日志监控配置（glob 自动发现）
│   ├── tools.py                 # 日志工具（LogListFilesTool + LogReadTool）
│   ├── agent.py                 # LogAlertAgent（批处理版）
│   ├── log_parser.py            # 日志解析器
│   ├── alerter.py               # 多渠道告警（console/mail/wecom）
│   └── run_log_check.py         # 完整检查流程
├── memory/
│   ├── history_store.py         # SQLiteHistoryStore（持久化历史存储 + Message 对象兼容）
│   ├── history.db               # SQLite 数据库（多会话隔离）
│   ├── sessions/                # 会话文件目录
│   └── traces/                  # 推理轨迹文件
├── weekly_report/
│   ├── session.py               # 业务会话状态机
│   ├── templates.py             # 周报 JSON schema
│   ├── excel_filler.py          # Excel 填写器
│   └── doc_parser.py            # Word 解析器
├── web/
│   ├── app.py                   # FastAPI 路由
│   ├── services.py              # FlowUs 服务层
│   └── weekly_services.py       # 周报服务层
└── cli.py                       # CLI 入口
```
