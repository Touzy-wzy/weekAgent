# weekAgent - FlowUs 智能周报助手

基于 [hello-agents](https://github.com/datawhalechina/hello-agents) 框架构建的智能体项目，将 FlowUs 工作空间访问、Excel 周报生成、邮件发送等能力封装为 Agent 工具，由 LLM 自主决策调用，实现"对话即周报"的自动化工作流。

## 核心功能

- **FlowUs 智能体对话**：LLM 自主选择工具、多步推理，回答用户关于 FlowUs 内容的问题
- **周报自动化工作流**：从 FlowUs 拉取素材 → 生成结构化数据 → 填写 Excel → 发送邮件，全流程 Agent 自主完成
- **多数据源支持**：FlowUs 自动拉取 或 用户上传 Word 文档解析
- **Web UI**：浏览器界面浏览页面树、查看内容、Agent 对话、周报会话管理
- **CLI 工具**：OAuth 授权、批量拉取 FlowUs 内容到本地
- **多轮对话记忆**：重写 ReActAgent 消息构建逻辑，注入历史对话，解决"说一句忘一句"问题
- **智能上下文压缩**：基于 GSSC 流水线的对话历史压缩，长会话不溢出

## 项目结构

```
weekAgent/
├── week_agent/                        # 主包
│   ├── config.py                      # 全局配置与路径常量
│   ├── cli.py                         # CLI / Web / Agent 入口逻辑
│   │
│   ├── flowus/                        # FlowUs 底层能力
│   │   ├── auth.py                    # OAuth 认证 + Token 持久化
│   │   ├── mcp_client.py              # MCP 客户端（首次授权用）
│   │   ├── http_client.py             # HTTP/JSON-RPC 客户端（Web/Agent 用）
│   │   └── utils.py                   # 数据解析工具函数
│   │
│   ├── agent/                         # Agent 层（基于 hello-agents）
│   │   ├── flowus_agent.py            # ReActAgent 子类：注入历史 + 修复 TraceLogger
│   │   ├── runner.py                  # Agent 创建与运行（含重试机制）
│   │   ├── prompts.py                 # 系统提示词（FlowUs 助手 + 周报助手）
│   │   └── tools/                     # Agent 工具集
│   │       ├── flowus_tools.py        # 列页面 / 取页面 / 语义搜索
│   │       ├── flowus_weekly_tool.py  # 按区间批量拉取周报素材
│   │       ├── fill_excel_tool.py     # 填写周报 Excel
│   │       ├── agently_mail_tools.py  # 邮件发送（两阶段确认 + 附件处理）
│   │       └── read_uploaded_doc_tool.py  # 读取上传的 Word 文件
│   │
│   ├── weekly_report/                 # 周报业务层
│   │   ├── session.py                 # 会话状态机（7 状态 + JSON 持久化）
│   │   ├── excel_filler.py            # openpyxl 填写 xlsx 模板
│   │   ├── templates.py               # 周报模板布局与数据校验
│   │   ├── doc_parser.py              # python-docx 解析 Word 文件
│   │   └── agent.py                   # 周报 Agent 业务逻辑
│   │
│   └── web/                           # Web UI 层
│       ├── app.py                     # FastAPI 路由
│       ├── services.py                # FlowUs 浏览 + Agent 对话服务
│       └── weekly_services.py         # 周报会话 + Agent 实例池
│
├── static/index.html                  # 前端单页应用
├── tests/                             # 测试套件
│   ├── test_flowus_tools.py
│   ├── test_mail_tools.py
│   ├── test_web.py
│   └── test_weekly_report.py
│
├── data/                              # 运行时数据（.gitignore 忽略）
│   ├── drafts/                        # 生成的周报 xlsx
│   ├── sessions/                      # 周报会话 JSON
│   └── uploads/                       # 上传的 Word 文件
│
├── memory/traces/                     # Agent 推理 trace（.gitignore 忽略）
├── run.py                             # 统一入口
├── debug_agent.py                     # Agent 调试脚本
├── requirements.txt
├── .env.example                       # 配置模板
└── .gitignore
```

## 安装

```bash
# 克隆项目
git clone https://github.com/Touzy-wzy/weekAgent.git
cd weekAgent

# 创建虚拟环境
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，填写以下配置：

```ini
# FlowUs MCP 配置
FLOWUS_MCP_URL=https://mcp.flowus.cn/message
FLOWUS_DEFAULT_PROJECT=积成电子

# LLM 配置（必需，用于 Agent 推理）
LLM_MODEL_ID=deepseek-ai/DeepSeek-V4-Flash
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api-inference.modelscope.cn/v1/

# 可选：搜索工具
SERPAPI_API_KEY=your-serpapi-key
MODELSCOPE_API_KEY=your-modelscope-key
```

### 外部工具依赖

- **agently-cli**：邮件发送工具依赖，需全局安装
  ```bash
  npm install -g agently-cli
  ```
- **FlowUs MCP**：首次使用需完成 OAuth 授权（见下文）

## 首次授权

首次使用 FlowUs 功能需完成 OAuth 授权，token 会持久化到 `.flowus_token.json`：

```bash
python run.py --list-tools
```

按提示在浏览器中完成授权。

## 使用方法

### 1. Web UI（推荐）

启动浏览器界面，包含 FlowUs 内容浏览、Agent 对话、周报生成全功能：

```bash
python run.py --web
# 访问 http://localhost:8000
```

**周报工作流**：
1. 在周报助手中输入"生成周报"
2. Agent 反问收集：填报人、周报区间、数据源（FlowUs / Word 上传）
3. 自动拉取素材 → 生成结构化数据 → 填写 Excel 草稿
4. 用户审核确认 → 提供收件人 → Agent 发送邮件

### 2. Agent 对话

```bash
# 单次查询
python run.py --agent "积成电子项目下有哪些页面?"

# 交互式调试（多轮对话）
python run.py --agent-debug

# 自定义最大推理步数
python run.py --agent "分析本周工作内容" --max-steps 10
```

### 3. CLI 拉取 FlowUs 内容

```bash
python run.py                                    # 默认路径
python run.py --path "/积成电子/2026.7.2"         # 指定路径
python run.py --output ./my_data                 # 指定输出目录
```

## API 端点

Web UI 启动后提供以下 REST API：

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 主页面 |
| GET | `/api/pages` | 列出项目页面树 |
| GET | `/api/page/{page_id}` | 获取页面 Markdown 内容 |
| GET | `/api/search?q=...` | 语义搜索工作空间 |
| POST | `/api/agent/chat?q=...` | FlowUs Agent 对话 |
| POST | `/api/weekly/sessions` | 创建周报会话 |
| GET | `/api/weekly/sessions` | 列出所有会话 |
| POST | `/api/weekly/sessions/{id}/message` | 周报会话对话 |
| POST | `/api/weekly/sessions/{id}/upload` | 上传 Word 文件 |
| GET | `/api/weekly/recipients` | 常用收件人列表 |

## Agent 工具

| 工具名 | 功能 | 关键参数 |
|--------|------|----------|
| `flowus_list_pages` | 列出项目下的所有子页面 | `project_name` |
| `flowus_get_page` | 获取页面 Markdown 内容 | `page_id` |
| `flowus_search` | 语义搜索工作空间 | `query` |
| `flowus_fetch_weekly` | 按区间批量拉取周报素材 | `project_name`, `week_range` |
| `fill_weekly_excel` | 填写周报 Excel 模板 | `reporter_name`, `week_range`, `report_data` |
| `agently_send_mail` | 发送邮件（自动两阶段确认） | `to`, `subject`, `body`, `attachment` |
| `agently_compose_mail` | 预览邮件内容（不发送） | `to`, `subject`, `body` |
| `read_uploaded_doc` | 读取上传的 Word 文件 | `session_id` |

## 架构说明

```
用户查询
  ↓
FlowUsAgent (ReActAgent 子类)
  ├── _build_messages: 注入历史对话（解决"说一句忘一句"）
  ├── run: 每次重置 TraceLogger（修复文件句柄关闭）
  └── _generate_smart_summary: 复用主 LLM 生成摘要
  ↓ LLM 推理决策
ToolRegistry (工具注册中心)
  ├── FlowUs 工具 → FlowUsHTTPClient → FlowUs MCP 服务器
  ├── 周报工具 → ExcelFiller / DocParser
  └── 邮件工具 → agently-cli (subprocess)
  ↓
Web 层 / CLI 层
  ├── services.py: Agent 实例池（按 session_id 复用，保持记忆）
  └── weekly_services.py: 周报会话状态机 + Agent 池
```

### 关键技术决策

1. **多轮对话记忆**：重写 `_build_messages` 把 `history_manager` 中的历史真正发给 LLM（hello-agents 原版只记录不发送）
2. **会话状态保持**：Web 层按 `session_id` 维护 Agent 实例池，复用实例累积对话历史
3. **智能上下文压缩**：超过 70% 上下文窗口时触发摘要，保留最近 6 轮完整对话
4. **邮件发送可靠性**：附件和 body 写入临时目录用 `--body-file` 传递，避免命令行参数解析问题；两阶段确认内部自动完成
5. **周报文件命名**：仅用区间最后一天日期（如 `2026.7.28` 而非 `2026.7.27-7.28`）

## 调试

```bash
# 工具单元测试（不依赖 LLM）
python debug_agent.py --tools

# 完整 Agent 测试（依赖 LLM）
python debug_agent.py --agent --query "积成电子下有哪些页面?"

# 运行 pytest 测试套件
pytest tests/

# 查看 Agent 推理 trace
# 位于 memory/traces/trace-s-*.jsonl
```

## 常见问题

### 邮件发送失败：确认令牌无效

**原因**：body 中的换行符或附件中文路径破坏了命令行参数解析。

**解决**：代码已自动将 body 写入临时文件用 `--body-file` 传递，附件复制到临时目录用相对路径传递。若仍失败，检查 agently-cli 是否正确安装。

### FlowUs API 返回 403 Forbidden

**原因**：机器人未被授权访问对应页面。

**解决**：在 FlowUs 中将机器人显式连接到目标项目/页面，邀请链接对机器人无效。

### LLM 返回 choices: null

**原因**：modelscope 等第三方网关偶发限流或内部错误。

**解决**：`run_query` 已内置自动重试机制（默认 2 次）。

### "说一句忘一句"问题

**原因**：hello-agents 原版 `_build_messages` 不发送历史消息。

**解决**：`FlowUsAgent` 已重写此方法，注入完整历史对话。

## 许可证

MIT License
