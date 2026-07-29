# weekAgent - FlowUs 智能体

基于 [hello-agents](https://github.com/datawhalechina/hello-agents) 框架，将 FlowUs 工作空间访问能力封装为 Agent 工具，支持 LLM 自主决策查询内容。

## 功能

- **Agent 对话**：LLM 自主选择工具、多步推理，回答用户关于 FlowUs 内容的问题
- **Web UI**：浏览器界面浏览页面树、查看内容、Agent 对话
- **CLI 工具**：OAuth 授权、批量拉取内容到本地
- **三个 Agent 工具**：列出页面 / 获取页面内容 / 语义搜索

## 项目结构

```
weekAgent/
├── week_agent/                    # 主包
│   ├── config.py                  # 配置与路径常量
│   ├── flowus/                    # FlowUs 底层能力
│   │   ├── auth.py                # OAuth 认证 + Token 持久化
│   │   ├── mcp_client.py          # MCP 客户端（首次授权用）
│   │   ├── http_client.py         # HTTP/JSON-RPC 客户端（Web/Agent 用）
│   │   └── utils.py               # 数据解析工具函数
│   ├── agent/                     # Agent 层（基于 hello-agents）
│   │   ├── tools/flowus_tools.py  # 三个 FlowUs 工具封装
│   │   ├── runner.py              # Agent 创建与运行
│   │   └── prompts.py             # 系统提示词
│   ├── web/                       # Web UI 层
│   │   ├── app.py                 # FastAPI 路由
│   │   └── services.py            # 业务服务（调用 Agent 工具）
│   └── cli.py                     # CLI 入口逻辑
├── static/index.html              # 前端
├── tests/                         # 测试
│   ├── test_flowus_tools.py       # Agent 工具单元测试
│   └── test_web.py                # Web API 测试
├── data/                          # 内容输出目录
├── run.py                         # 统一入口
├── debug_agent.py                 # Agent 调试脚本
├── requirements.txt
└── .env                           # 配置（需自行填写）
```

## 安装

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，填写：

```ini
# FlowUs MCP
FLOWUS_MCP_URL=https://mcp.flowus.cn/message
FLOWUS_DEFAULT_PROJECT=积成电子

# LLM 配置（必需，用于 Agent）
LLM_MODEL_ID=deepseek-ai/DeepSeek-V4-Flash
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api-inference.modelscope.cn/v1/
```

## 首次授权

首次使用需完成 OAuth 授权，token 会持久化到 `.flowus_token.json`：

```bash
python run.py --list-tools
```

按提示在浏览器中完成授权。

## 使用方法

### 1. Agent 对话（核心）

```bash
# 单次查询
python run.py --agent "积成电子项目下有哪些页面?"

# 交互式调试
python run.py --agent-debug
```

### 2. Web UI

```bash
python run.py --web
# 访问 http://localhost:8000
```

API 端点：
- `GET /api/pages` - 列出项目页面
- `GET /api/page/{page_id}` - 获取页面内容
- `GET /api/search?q=...` - 语义搜索
- `POST /api/agent/chat?q=...` - Agent 对话

### 3. CLI 拉取

```bash
python run.py                                    # 默认路径
python run.py --path "/积成电子/2026.7.2"         # 指定路径
python run.py --output ./my_data                 # 指定输出目录
```

### 4. 调试

```bash
# 工具单元测试（不依赖 LLM）
python debug_agent.py --tools

# 完整 Agent 测试（依赖 LLM）
python debug_agent.py --agent --query "积成电子下有哪些页面?"

# 运行 pytest
pytest tests/
```

## Agent 工具

| 工具名 | 功能 | 参数 |
|---|---|---|
| `flowus_list_pages` | 列出项目下的所有子页面 | `project_name` |
| `flowus_get_page` | 获取页面 Markdown 内容 | `page_id` |
| `flowus_search` | 语义搜索工作空间 | `query` |

## 架构说明

```
用户查询
  ↓
ReActAgent (hello-agents)
  ↓ LLM 推理决策
FlowUs 工具 (flowus_tools.py)
  ↓ 同步 run() → 线程池 → async
FlowUsHTTPClient (http_client.py)
  ↓ HTTP/JSON-RPC
FlowUs MCP 服务器
```

Web UI 的 `/api/pages` 等端点直接调用工具层（不过 LLM），`/api/agent/chat` 走完整 Agent 流程。

## 许可证

MIT License
