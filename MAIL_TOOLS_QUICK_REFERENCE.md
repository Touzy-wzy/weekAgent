# 邮件工具快速参考

## 工具注册

```python
from week_agent.agent.tools import (
    AgentlyComposeMailTool, 
    AgentlySendMailTool
)

registry.register_tool(AgentlyComposeMailTool())
registry.register_tool(AgentlySendMailTool())
```

## 工具调用流程

### 第1步: 编写邮件

**工具名**: `agently_compose_mail`

**参数**:
- `to`: 收件人邮箱 (可多个，用逗号分隔)
- `subject`: 邮件主题
- `body`: 邮件内容

**返回**:
```
{
  confirmation_token: "ctk_xxxx",
  to, subject, body,
  summary: {...}
}
```

### 第2步: 发送邮件

**工具名**: `agently_send_mail`

**参数**:
- `to`: 收件人邮箱
- `subject`: 邮件主题  
- `body`: 邮件内容
- `confirmation_token`: 第1步返回的令牌

**返回**:
```
{
  queued: true,
  to, subject
}
```

## Agent 对话示例

```
用户: 帮我给 alice@example.com 发邮件，标题"会议通知"，内容"明天下午3点开会"

Agent 内部流程:
1. 调用 agently_compose_mail(
     to="alice@example.com",
     subject="会议通知", 
     body="明天下午3点开会"
   )
   
2. 获得确认令牌，向用户展示预览
   
3. 用户同意后，调用 agently_send_mail(
     to="alice@example.com",
     subject="会议通知",
     body="明天下午3点开会",
     confirmation_token="ctk_xxxx"
   )
   
4. 返回发送成功状态

用户: 好的，邮件已发送
```

## 文件位置

- 工具实现: `week_agent/agent/tools/agently_mail_tools.py`
- 工具导出: `week_agent/agent/tools/__init__.py`
- 工具注册: `week_agent/agent/runner.py`
- 使用文档: `MAIL_TOOLS_USAGE.md`
- 集成说明: `MAIL_TOOLS_INTEGRATION.md`
- 测试代码: `tests/test_mail_tools.py`

## 重要提示

- 邮件发送需要先通过 OAuth 授权
  ```bash
  agently-cli auth login
  ```

- API 配额限制:
  - 每天: 50 封
  - 每分钟: 10 次请求
  - 每小时: 200 次请求

- 邮件发送是异步的，调用后立即返回，实际投递在后台进行

## 错误处理

工具返回的 `response.status` 可能为:

| 状态 | 说明 |
|------|------|
| `ToolStatus.SUCCESS` | 操作成功 |
| `ToolStatus.ERROR` | 操作失败，查看 `error_info` |
| `ToolStatus.PARTIAL` | 部分成功 |

错误信息在 `response.error_info['message']` 中
