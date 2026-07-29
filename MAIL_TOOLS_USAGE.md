# 邮件工具使用指南

## 概述

`agently-mail-tools` 提供两个 Agent 工具来处理邮件发送：

1. **agently_compose_mail** - 编写邮件（获取确认令牌）
2. **agently_send_mail** - 发送邮件（使用确认令牌）

这种两步流程设计确保：
- 用户可以在发送前预览邮件内容
- 避免意外发送错误的邮件
- 提高邮件发送的安全性和准确性

## 工具参数

### agently_compose_mail（编写邮件）

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `to` | string | ✓ | 收件人邮箱，多个邮箱用逗号分隔 |
| `subject` | string | ✓ | 邮件主题 |
| `body` | string | ✓ | 邮件正文内容 |

**返回数据：**
```json
{
  "confirmation_token": "ctk_xxxxxx",
  "to": "user@example.com",
  "subject": "邮件主题",
  "body": "邮件内容",
  "summary": {
    "to": ["user@example.com"],
    "subject": "邮件主题",
    "attachment_count": 0
  }
}
```

### agently_send_mail（发送邮件）

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `to` | string | ✓ | 收件人邮箱 |
| `subject` | string | ✓ | 邮件主题 |
| `body` | string | ✓ | 邮件正文内容 |
| `confirmation_token` | string | ✓ | 确认令牌（来自 agently_compose_mail） |

**返回数据：**
```json
{
  "queued": true,
  "to": "user@example.com",
  "subject": "邮件主题"
}
```

## 使用示例

### 场景 1：直接对话发送邮件

**用户输入：** "帮我发一封邮件给 john@example.com，主题是 '项目进展'，内容是 '项目进度良好，预计明天完成'"

**Agent 流程：**

1. Agent 调用 `agently_compose_mail`
   ```
   参数：
   - to: "john@example.com"
   - subject: "项目进展"
   - body: "项目进度良好，预计明天完成"
   ```

2. Agent 收到确认令牌和邮件预览，回复用户：
   ```
   我已准备好发送以下邮件：
   - 收件人: john@example.com
   - 主题: 项目进展
   - 内容字数: 0 附件
   
   确认无误后，将使用确认令牌发送邮件。
   ```

3. 用户确认无误后，Agent 调用 `agently_send_mail`
   ```
   参数：
   - to: "john@example.com"
   - subject: "项目进展"
   - body: "项目进度良好，预计明天完成"
   - confirmation_token: "ctk_cd562ca4-..."
   ```

4. 邮件成功发送，Agent 回复：
   ```
   邮件已成功发送！
   - 收件人: john@example.com
   - 主题: 项目进展
   - 状态: 已入队处理
   ```

### 场景 2：发送给多个收件人

**用户输入：** "给 alice@example.com 和 bob@example.com 发邮件，标题 '会议通知'，内容 '明天下午 3 点开会'"

**Agent 流程：**

1. 编写邮件（多个收件人用逗号分隔）
   ```
   - to: "alice@example.com,bob@example.com"
   - subject: "会议通知"
   - body: "明天下午 3 点开会"
   ```

2. 预览并确认后发送

## 工作流程图

```
用户输入邮件请求
        ↓
   [编写邮件]
   agently_compose_mail
        ↓
  获取确认令牌 + 预览
        ↓
    用户确认
        ↓
   [发送邮件]
   agently_send_mail
   (使用确认令牌)
        ↓
    邮件已入队
        ↓
    任务完成
```

## 错误处理

### 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| "收件人不能为空" | 未提供 `to` 参数 | 指定至少一个有效的邮箱地址 |
| "邮件主题不能为空" | 未提供 `subject` 参数 | 提供邮件主题 |
| "邮件内容不能为空" | 未提供 `body` 参数 | 提供邮件正文内容 |
| "确认令牌不能为空" | 发送时缺少确认令牌 | 先调用编写工具获取令牌 |
| "agently-cli not found" | 未安装 agently-cli | 运行 `npm install -g @tencent-qqmail/agently-cli` |
| "认证失败" | agently-cli 未授权 | 运行 `agently-cli auth login` 进行授权 |

## 限制

根据 Agently API 的配额限制：

- **每日发送限额：** 50 封邮件
- **每分钟请求限制：** 10 次请求
- **每小时请求限制：** 200 次请求
- **单个附件最大：** 20 MB
- **单个邮件最大总附件：** 20 MB

## 代码集成示例

### 在 Agent 中注册工具

```python
from hello_agents import ToolRegistry, ReActAgent
from week_agent.agent.tools import AgentlyComposeMailTool, AgentlySendMailTool

# 创建工具注册表
registry = ToolRegistry()
registry.register_tool(AgentlyComposeMailTool())
registry.register_tool(AgentlySendMailTool())

# 创建 Agent
agent = ReActAgent(
    name="邮件助手",
    llm=your_llm,
    tool_registry=registry,
    system_prompt="你是一个邮件助手，可以帮助用户编写和发送邮件。"
)

# 运行
result = agent.run("帮我发邮件给 user@example.com")
```

### 直接调用工具

```python
from week_agent.agent.tools import AgentlyComposeMailTool, AgentlySendMailTool

# 编写邮件
compose_tool = AgentlyComposeMailTool()
compose_response = compose_tool.run({
    "to": "user@example.com",
    "subject": "测试邮件",
    "body": "这是一封测试邮件"
})

# 检查响应
if compose_response.is_success():
    confirmation_token = compose_response.data["confirmation_token"]
    
    # 发送邮件
    send_tool = AgentlySendMailTool()
    send_response = send_tool.run({
        "to": "user@example.com",
        "subject": "测试邮件",
        "body": "这是一封测试邮件",
        "confirmation_token": confirmation_token
    })
    
    if send_response.is_success():
        print("邮件已发送！")
```

## 调试

### 查看命令行输出

工具会在控制台打印详细的调试信息：

```
✏️ [agently_compose_mail] 编写邮件
   收件人: user@example.com
   主题: 测试
   内容长度: 10 字符
  ✅ 邮件编写完成，等待确认

📧 [agently_send_mail] 发送邮件
   收件人: user@example.com
   主题: 测试
   令牌: ctk_cd562ca4...
  ✅ 邮件已成功发送（入队）
```

### 获取更多调试信息

修改 runner.py 以输出详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```
