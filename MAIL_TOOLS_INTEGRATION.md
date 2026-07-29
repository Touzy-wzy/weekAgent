# 邮件工具集成完成

已成功将 Agently CLI 邮件功能封装为 hello-agents 工具框架中的两个独立工具。

## 已完成工作

### 1. 创建邮件工具文件
- 文件位置: [agently_mail_tools.py](week_agent/agent/tools/agently_mail_tools.py)
- 包含两个工具类:
  - `AgentlyComposeMailTool` - 邮件编写（获取确认令牌）
  - `AgentlySendMailTool` - 邮件发送（使用确认令牌）

### 2. 工具集成
- 更新 [tools/__init__.py](week_agent/agent/tools/__init__.py) 导出新工具
- 更新 [runner.py](week_agent/agent/runner.py) 在工具注册表中注册邮件工具

### 3. 创建文档
- [MAIL_TOOLS_USAGE.md](MAIL_TOOLS_USAGE.md) - 完整使用指南
- [tests/test_mail_tools.py](tests/test_mail_tools.py) - 集成测试脚本

## 工具设计

### 两步流程设计

为了确保邮件发送的安全性，采用了两步流程:

```
用户请求
    ↓
[1] AgentlyComposeMailTool (编写邮件)
    - 参数: to, subject, body
    - 返回: 确认令牌 + 邮件预览
    ↓
用户确认
    ↓
[2] AgentlySendMailTool (发送邮件)
    - 参数: to, subject, body, confirmation_token
    - 返回: 发送状态（已入队）
    ↓
任务完成
```

### API 集成

工具内部通过 subprocess 调用 `agently-cli` 命令:

```bash
# 编写邮件 (获取确认令牌)
agently-cli message +send --to recipient@example.com --subject "Title" --body "Content"

# 发送邮件 (使用确认令牌)
agently-cli message +send --to recipient@example.com --subject "Title" --body "Content" --confirmation-token TOKEN
```

## 在 Agent 中使用

### 注册工具

```python
from hello_agents import ReActAgent, ToolRegistry
from week_agent.agent.tools import AgentlyComposeMailTool, AgentlySendMailTool

# 创建工具注册表
registry = ToolRegistry()
registry.register_tool(AgentlyComposeMailTool())
registry.register_tool(AgentlySendMailTool())

# 创建 Agent
agent = ReActAgent(
    name="邮件助手",
    llm=llm,
    tool_registry=registry,
    system_prompt="你是一个邮件助手..."
)
```

### Agent 工作流示例

**用户**: "帮我发邮件给 john@example.com，标题 'Project Update'，内容 'Project is on track'"

**Agent 流程**:

1. 调用 `agently_compose_mail` 工具
2. 获取确认令牌和邮件预览
3. 向用户展示预览内容
4. 用户确认后，调用 `agently_send_mail` 工具
5. 使用确认令牌发送邮件
6. 返回发送状态给用户

## 工具参数

### AgentlyComposeMailTool

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `to` | string | ✓ | 收件人邮箱，多个用逗号分隔 |
| `subject` | string | ✓ | 邮件主题 |
| `body` | string | ✓ | 邮件正文 |

**返回** (成功):
```json
{
  "confirmation_token": "ctk_xxxxx",
  "to": "recipient@example.com",
  "subject": "Email Subject",
  "body": "Email body content",
  "summary": {
    "to": ["recipient@example.com"],
    "subject": "Email Subject",
    "attachment_count": 0
  }
}
```

### AgentlySendMailTool

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `to` | string | ✓ | 收件人邮箱 |
| `subject` | string | ✓ | 邮件主题 |
| `body` | string | ✓ | 邮件正文 |
| `confirmation_token` | string | ✓ | 确认令牌 (来自 compose 工具) |

**返回** (成功):
```json
{
  "queued": true,
  "to": "recipient@example.com",
  "subject": "Email Subject"
}
```

## 运行时依赖

- `agently-cli` 已安装并授权 (见主 README)
- 邮箱账户已通过 OAuth 认证
- 网络连接正常

## 错误处理

工具会返回 `ToolResponse` 对象，状态为:
- `ToolStatus.SUCCESS` - 操作成功
- `ToolStatus.ERROR` - 操作失败 (包含错误信息)
- `ToolStatus.PARTIAL` - 部分成功

## 安全特性

1. **两步确认流程** - 防止误发邮件
2. **参数验证** - 所有参数都进行非空检查
3. **令牌验证** - 发送前必须提供有效的确认令牌
4. **错误处理** - 异常被捕获并返回清晰的错误信息
5. **日志输出** - 所有操作都有调试输出便于排查问题

## 扩展可能性

未来可以扩展的功能:

- 支持附件上传 (已在 agently-cli 中支持)
- 邮件模板系统
- 草稿保存
- 邮件搜索和回复
- 批量发送
- 定时发送

## 测试

运行集成测试 (需要 agently-cli 授权):

```bash
cd e:\weekAgent
source venv/Scripts/activate
PYTHONPATH=. python tests/test_mail_tools.py
```

## 注意事项

- 工具通过子进程调用 `agently-cli`，确保与 Agent 的事件循环隔离
- 邮件发送是异步的，调用后立即返回，实际发送在后台进行
- 受 Agently API 配额限制 (日限 50 封，分钟限 10 次请求)
