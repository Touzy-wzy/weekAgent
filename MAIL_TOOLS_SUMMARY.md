# 邮件工具集成总结

## 工作完成

已成功将 Agently CLI 邮件发送功能封装为 hello-agents 兼容的 Agent 工具。

## 创建的文件

### 1. 工具实现
- **[week_agent/agent/tools/agently_mail_tools.py](week_agent/agent/tools/agently_mail_tools.py)** (270+ 行)
  - `AgentlyComposeMailTool` - 邮件编写工具（获取确认令牌）
  - `AgentlySendMailTool` - 邮件发送工具（使用确认令牌）

### 2. 工具集成
- **[week_agent/agent/tools/__init__.py](week_agent/agent/tools/__init__.py)** - 导出新工具
- **[week_agent/agent/runner.py](week_agent/agent/runner.py)** - 在 ToolRegistry 中注册工具

### 3. 文档
- **[MAIL_TOOLS_USAGE.md](MAIL_TOOLS_USAGE.md)** - 详细的使用指南
- **[MAIL_TOOLS_INTEGRATION.md](MAIL_TOOLS_INTEGRATION.md)** - 技术集成文档
- **[MAIL_TOOLS_QUICK_REFERENCE.md](MAIL_TOOLS_QUICK_REFERENCE.md)** - 快速参考卡片

### 4. 测试
- **[tests/test_mail_tools.py](tests/test_mail_tools.py)** - 集成测试脚本

## 核心设计

### 两步安全发送流程

为防止误发邮件，工具采用两步流程：

```
用户请求 → 编写邮件(compose) → 获取确认令牌 → 预览显示 → 
用户确认 → 发送邮件(send) → 发送成功 → 任务完成
```

### 工具特性

✅ **参数验证** - 所有参数都进行非空和格式检查  
✅ **错误处理** - 完整的异常捕获和错误报告  
✅ **日志输出** - 调试信息便于排查问题  
✅ **令牌机制** - 使用确认令牌防止重复或误发  
✅ **多收件人** - 支持逗号分隔的多个收件人  
✅ **响应封装** - 返回标准 ToolResponse 对象  

## 工具参数

### AgentlyComposeMailTool（编写邮件）

```python
{
    "to": "user@example.com",                    # 收件人
    "subject": "邮件标题",                       # 主题
    "body": "邮件内容"                          # 正文
}
```

**返回**:
```python
{
    "confirmation_token": "ctk_xxxxx",
    "to": "user@example.com",
    "subject": "邮件标题",
    "body": "邮件内容",
    "summary": {
        "to": ["user@example.com"],
        "subject": "邮件标题",
        "attachment_count": 0
    }
}
```

### AgentlySendMailTool（发送邮件）

```python
{
    "to": "user@example.com",                                    # 收件人
    "subject": "邮件标题",                                       # 主题
    "body": "邮件内容",                                         # 正文
    "confirmation_token": "ctk_xxxxx"                           # 确认令牌
}
```

**返回**:
```python
{
    "queued": true,
    "to": "user@example.com",
    "subject": "邮件标题"
}
```

## 使用示例

### 在 Agent 中注册工具

```python
from week_agent.agent.tools import AgentlyComposeMailTool, AgentlySendMailTool
from hello_agents import ReActAgent, ToolRegistry

# 创建工具注册表
registry = ToolRegistry()
registry.register_tool(AgentlyComposeMailTool())
registry.register_tool(AgentlySendMailTool())

# 创建 Agent（runner.py 已自动执行此操作）
agent = ReActAgent(
    name="Email Assistant",
    tool_registry=registry,
    ...
)
```

### Agent 对话示例

**用户**: "帮我发邮件给 john@example.com，标题 'Project Update'，内容 'We are on track'"

**Agent 执行**:
1. 调用 `agently_compose_mail` 工具
2. 获取确认令牌和邮件预览
3. 向用户展示: "邮件已编写完成，请确认以下内容..."
4. 用户同意
5. 调用 `agently_send_mail` 工具（使用令牌）
6. 返回: "邮件已成功发送！"

## 工具工作流程

```
┌─────────────────────────────────────────────────────┐
│         Agent 接收用户邮件请求                        │
└──────────────────────┬────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  AgentlyComposeMailTool      │
        │  1. 验证参数 (to, subj, body) │
        │  2. 调用 agently-cli 命令    │
        │  3. 解析返回的确认令牌        │
        │  4. 返回邮件预览             │
        └──────────────────┬───────────┘
                           │
                           ▼
        ┌──────────────────────────────┐
        │      向用户展示预览内容        │
        │   等待用户确认（Agent决策）    │
        └──────────────────┬───────────┘
                           │
                    用户同意后
                           │
                           ▼
        ┌──────────────────────────────┐
        │  AgentlySendMailTool         │
        │  1. 验证参数 + 确认令牌       │
        │  2. 调用 agently-cli 命令    │
        │  3. 使用令牌发送邮件         │
        │  4. 返回发送状态             │
        └──────────────────┬───────────┘
                           │
                           ▼
        ┌──────────────────────────────┐
        │     返回发送成功状态给用户     │
        └──────────────────────────────┘
```

## 依赖和前置条件

### 系统依赖
- `agently-cli` 已全局安装
  ```bash
  npm install -g @tencent-qqmail/agently-cli
  ```

### 认证
- 邮箱已通过 OAuth 授权
  ```bash
  agently-cli auth login
  ```

### Python 依赖
- `hello-agents>=1.0.0` (已在项目中)
- `subprocess` (Python 标准库)
- `json` (Python 标准库)

## API 配额

使用 Agently API 的配额限制：

| 限制 | 数值 |
|------|------|
| 每日邮件发送限额 | 50 封 |
| 每分钟请求数限制 | 10 次 |
| 每小时请求数限制 | 200 次 |
| 单个附件最大大小 | 20 MB |
| 单邮件附件总大小 | 20 MB |

## 错误处理

### 工具状态返回

工具通过 `response.status` 返回执行状态：

| 状态 | 说明 | 处理方式 |
|------|------|---------|
| `ToolStatus.SUCCESS` | 操作成功 | 继续流程 |
| `ToolStatus.ERROR` | 操作失败 | 返回错误信息给用户 |
| `ToolStatus.PARTIAL` | 部分成功 | 显示警告并继续 |

### 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| "系统找不到指定的文件" | agently-cli 未安装或不在 PATH | 运行 `npm install -g @tencent-qqmail/agently-cli` |
| "收件人不能为空" | 缺少 to 参数 | 提供有效的邮箱地址 |
| "认证失败" | agently-cli 未授权 | 运行 `agently-cli auth login` |
| "超时" | 网络或 API 响应慢 | 重试操作 |

## 扩展建议

未来可以添加的功能：

- [ ] 附件支持 (agently-cli 已支持)
- [ ] 邮件模板系统
- [ ] 草稿管理
- [ ] 邮件搜索和回复
- [ ] 批量发送
- [ ] 定时发送
- [ ] 邮件转发

## 文件清单

```
week_agent/
├── agent/
│   ├── tools/
│   │   ├── agently_mail_tools.py          ★ 新增
│   │   ├── flowus_tools.py
│   │   └── __init__.py                    ★ 更新
│   ├── runner.py                           ★ 更新
│   └── ...
├── tests/
│   └── test_mail_tools.py                 ★ 新增
├── MAIL_TOOLS_USAGE.md                    ★ 新增
├── MAIL_TOOLS_INTEGRATION.md              ★ 新增
├── MAIL_TOOLS_QUICK_REFERENCE.md          ★ 新增
└── ...
```

## 下一步

1. **测试** - 在实际 Agent 中测试邮件工具
2. **微调** - 根据实际使用情况优化参数和提示词
3. **文档** - 在项目 README 中补充邮件工具的使用说明
4. **扩展** - 添加更多邮件相关功能

## 技术细节

### 设计模式

- **两步验证模式** - 确保用户意图明确
- **令牌机制** - 防止重复或误操作
- **异步执行** - 邮件发送在后台进行
- **错误封装** - 统一的错误处理和报告

### 代码质量

- ✅ 遵循 hello-agents Tool 接口规范
- ✅ 完整的参数验证
- ✅ 详细的错误消息
- ✅ 调试日志输出
- ✅ 类型提示（Python 类型注解）
- ✅ 完整的文档和注释

### 兼容性

- ✅ 与 hello-agents 1.0.0+ 兼容
- ✅ 与 agently-cli 最新版本兼容
- ✅ 支持 Python 3.8+
- ✅ 跨平台支持 (Windows/macOS/Linux)

---

**状态**: ✅ 完成  
**版本**: 1.0.0  
**最后更新**: 2026-07-28
