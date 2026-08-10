# -*- coding: utf-8 -*-
"""日志模板库 - 按模块+级别组织，模拟生产环境日志

模板变量说明：
  {agent_id}      - 智能体 ID，如 agent-259827c23167
  {uuid}          - 通用唯一 ID，如 3209466
  {task_id}       - 任务 ID，如 a37f6c770a0e
  {callback_url}  - 回调地址
  {step}          - 步骤编号 (1-10)
  {tool_name}     - 工具名称
  {n}             - 数量 (1-20)
  {path}          - 文件路径
  {error_msg}     - 错误信息
  {http_status}   - HTTP 状态码
  {user_id}       - 用户 ID
  {thought}       - 思考内容
  {result}        - 执行结果摘要
  {duration}      - 耗时(ms)
  {size}          - 文件大小
  {name}          - 文件名
  {type}          - 文件类型
  {db_table}      - 数据库表名
  {query_time}    - 查询耗时(ms)
  {cache_key}     - 缓存键
  {endpoint}      - API 端点
  {method}        - HTTP 方法
  {ip}            - IP 地址
  {session_id}    - 会话 ID
  {memory_type}   - 记忆类型
  {skill_name}    - 技能名称
  {contract_name} - 合同名称
"""

import random

# ---------------------------------------------------------------------------
# 可替换的变量池（生成时随机抽取）
# ---------------------------------------------------------------------------

AGENT_IDS = [
    "agent-259827c23167", "agent-3a8b1c9d2e45", "agent-7f6e5d4c3b2a",
    "agent-bc89d0123456", "agent-1a2b3c4d5e6f",
]

CALLBACK_URLS = [
    "https://msc.ieslab.cn/api/external/oa/callback",
    "https://api.example.com/webhook/callback",
    "https://gateway.ieslab.cn/api/v2/callback",
]

TOOL_NAMES = [
    "文件读取_parse_documents", "terminal", "Skill", "web_search",
    "database_query", "api_call", "file_upload", "email_send",
    "image_ocr", "text_translate",
]

ERROR_MESSAGES = [
    "连接超时: 目标服务器无响应",
    "权限不足: 用户未授权访问该资源",
    "文件解析失败: 不支持的文件格式",
    "数据库连接池耗尽: 无可用连接",
    "API 调用失败: 返回状态码 500",
    "内存不足: 无法分配缓冲区",
    "读取文件失败: 文件被占用或已删除",
    "JSON 解析错误: 格式不正确",
    "网络不可达: DNS 解析失败",
    "请求频率超限: 触发限流机制",
]

THOUGHTS = [
    "用户希望我提取合同中的信息。我需要先解析文件，再调用信息提取技能。",
    "收到一个数据分析请求，需要查询数据库获取原始数据。",
    "用户要求生成报告，我先整理数据再调用模板渲染。",
    "需要调用外部 API 获取实时数据，然后进行格式化处理。",
    "检测到异常日志，需要分析根因并给出修复建议。",
    "用户上传了一个文件，我先识别文件类型再选择合适的解析器。",
    "需要将结果转换为用户友好的格式，考虑使用 Markdown 表格。",
    "当前任务涉及多个步骤，需要按顺序执行并记录中间结果。",
    "用户的请求比较模糊，我需要先澄清需求再执行。",
    "这是一个复杂的查询，需要拆分为多个子任务逐步完成。",
]

RESULTS = [
    "工具 'parse_documents' 执行成功，已解析文件内容。",
    "查询完成，返回 15 条记录，耗时 230ms。",
    "API 调用成功，返回数据大小 2.3KB。",
    "文件上传完成，存储路径: /app/uploads/ext_api_xxx/",
    "搜索完成，找到 8 条相关结果。",
    "翻译完成，原文 120 字符 -> 目标语言 98 字符。",
    "文档生成完成，已保存到 /app/outputs/report_20260807.pdf。",
    "OCR 识别完成，提取文本 450 字符。",
    "邮件发送成功，收件人: user@example.com。",
    "数据写入完成，影响行数: 3。",
]

FILE_NAMES = [
    "511949b3-4f39-4e33-9f56-70ce96181d1c_合同.docx",
    "data_report_2026Q3.xlsx",
    "meeting_minutes_20260807.pdf",
    "product_image_001.png",
    "api_specification_v2.json",
    "user_manual_v3.1.docx",
    "sales_data_2026H1.csv",
    "architecture_diagram.png",
    "deployment_config.yaml",
    "log_analysis_report.html",
]

FILE_TYPES = [".docx", ".xlsx", ".pdf", ".png", ".json", ".csv", ".yaml", ".html", ".txt", ".pptx"]

DB_TABLES = [
    "user_info", "order_records", "product_catalog", "agent_sessions",
    "task_queue", "log_entries", "config_store", "audit_trail",
]

ENDPOINTS = [
    "/api/v1/agent/run", "/api/v1/data/query", "/api/v1/file/upload",
    "/api/v2/user/info", "/api/internal/task/status", "/api/external/oa/callback",
    "/api/v1/search", "/api/v1/export", "/api/v2/analyze",
]

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]

IPS = [
    "192.168.1.100", "10.0.0.55", "172.16.0.23", "192.168.2.88",
    "10.10.1.200", "172.20.0.15",
]

MEMORY_TYPES = ["['episodic']", "['semantic']", "['episodic', 'semantic']", "['procedural']"]

SKILL_NAMES = [
    "合同信息提取器(JSON)", "数据分析报告生成", "文档内容摘要",
    "代码审查助手", "翻译引擎", "图片文字识别",
]

# ---------------------------------------------------------------------------
# 日志模板（按模块 + 级别组织）
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, list[str]]] = {
    # ========================================================================
    # app.api.public_api - 外部 API 入口
    # ========================================================================
    "app.api.public_api": {
        "INFO": [
            "收到外部调用请求 [异步模式] agent_id={agent_id} uuid={uuid} 回调地址={callback_url} 附件数={n}",
            "收到外部调用请求 [同步模式] agent_id={agent_id} uuid={uuid}",
            "附件存储路径: {path}",
            "异步任务已创建并投递 task_id={task_id} agent_id={agent_id}",
            "请求参数验证通过 agent_id={agent_id} method={method}",
            "收到 {n} 个文件上传请求 agent_id={agent_id}",
            "文件校验通过: name={name}, size={size} bytes, type={type}",
            "回调地址可达性检查通过 url={callback_url}",
            "请求认证成功 user_id={user_id} token_type=bearer",
            "请求体大小: {size} bytes, 接口: {endpoint}",
        ],
        "WARNING": [
            "请求频率较高 agent_id={agent_id} 当前QPS={n}",
            "回调地址响应较慢 url={callback_url} 耗时={duration}ms",
            "附件大小超过建议值: {size} bytes, 建议压缩",
            "请求缺少可选字段: user_agent, 使用默认值",
            "认证令牌即将过期 user_id={user_id} 剩余有效时间={n}分钟",
        ],
        "ERROR": [
            "外部调用失败 agent_id={agent_id} 错误: {error_msg}",
            "回调地址不可达 url={callback_url} status={http_status}",
            "文件上传失败 agent_id={agent_id} 错误: {error_msg}",
            "请求认证失败 user_id={user_id} 原因: token_invalid",
            "请求体解析失败: JSON 格式错误 endpoint={endpoint}",
            "请求频率超限 agent_id={agent_id} 已被临时限流",
            "参数校验失败 agent_id={agent_id} 缺少必要字段: agent_id",
        ],
    },

    # ========================================================================
    # app.services.async_runner - 异步任务执行器
    # ========================================================================
    "app.services.async_runner": {
        "INFO": [
            "任务 {task_id} 附件数={n}",
            "开始执行异步任务 task_id={task_id} agent_id={agent_id} 回调地址={callback_url}",
            "任务 {task_id} 执行完成 耗时={duration}ms",
            "任务 {task_id} 结果已推送至回调地址 status=200",
            "任务 {task_id} 进入队列等待 position={n}",
            "任务进度更新 task_id={task_id} 当前步骤 {step}/{n}",
            "任务 {task_id} 上下文保存完成 session_id={session_id}",
        ],
        "WARNING": [
            "任务 {task_id} 执行时间较长 耗时={duration}ms 超过阈值",
            "任务队列深度过高 当前排队任务数={n}",
            "任务 {task_id} 回调重试 第{n}次 上次失败原因: timeout",
            "任务 {task_id} 使用降级模型 原模型不可用",
        ],
        "ERROR": [
            "任务 {task_id} 执行失败: {error_msg}",
            "任务 {task_id} 回调推送失败 status={http_status} 已重试{n}次",
            "任务 {task_id} 超时取消 执行时间={duration}ms 超过最大限制",
            "任务 {task_id} 附件下载失败: {error_msg}",
        ],
    },

    # ========================================================================
    # app.services.agent_runtime.runtime - Agent 运行时
    # ========================================================================
    "app.services.agent_runtime.runtime": {
        "INFO": [
            "[步骤] 步骤 {step} 开始",
            "[思考] {thought}",
            "[工具调用] 步骤 {step} | 工具: {tool_name} | 结果: {result}",
            "[步骤] 步骤 {step} 完成 耗时={duration}ms",
            "[完成] 所有步骤执行完毕 总步骤={n} 总耗时={duration}ms",
            "[工具调用] 步骤 {step} | 工具: {tool_name} | 耗时={duration}ms",
            "Agent 会话创建 session_id={session_id} agent_id={agent_id}",
            "Agent 上下文加载完成 session_id={session_id} 历史消息数={n}",
            "Agent 模型切换 to={tool_name} 原因: 任务复杂度提升",
            "Agent 输出解析完成 输出长度={n} 字符",
        ],
        "WARNING": [
            "[思考] 步骤 {step} 推理时间较长 耗时={duration}ms",
            "[工具调用] 步骤 {step} | 工具: {tool_name} | 返回结果过大 size={size} bytes",
            "Agent 上下文窗口使用率 {n}% 接近上限",
            "Agent 检测到可能循环 连续相似输出={n}次",
        ],
        "ERROR": [
            "[错误] 步骤 {step} 执行失败: {error_msg}",
            "[工具调用] 步骤 {step} | 工具: {tool_name} | 失败: {error_msg}",
            "Agent 执行异常 session_id={session_id} 错误: {error_msg}",
            "Agent 模型调用失败 重试次数={n} 错误: {error_msg}",
        ],
    },

    # ========================================================================
    # ies_agents.memory.manager - 记忆管理
    # ========================================================================
    "ies_agents.memory.manager": {
        "INFO": [
            "MemoryManager初始化完成，启用记忆类型: {memory_type}",
            "记忆写入成功 session_id={session_id} 类型={memory_type}",
            "记忆检索完成 session_id={session_id} 返回{n}条相关记录",
            "记忆压缩完成 session_id={session_id} 压缩前{n}条 -> 压缩后{n}条",
            "记忆过期清理完成 清理{n}条过期记录",
            "记忆上下文注入完成 session_id={session_id} 注入{n}条记忆",
        ],
        "WARNING": [
            "记忆存储空间使用率 {n}% 建议清理",
            "记忆检索耗时较长 {duration}ms session_id={session_id}",
            "记忆压缩率偏低 仅减少{n}% 建议调整阈值",
        ],
        "ERROR": [
            "记忆存储失败 session_id={session_id} 错误: {error_msg}",
            "记忆检索异常 session_id={session_id} 错误: {error_msg}",
            "记忆压缩失败 session_id={session_id} 原因: 数据格式异常",
        ],
    },

    # ========================================================================
    # app.services.database - 数据库服务
    # ========================================================================
    "app.services.database": {
        "INFO": [
            "数据库查询完成 table={db_table} 耗时={query_time}ms 返回{n}行",
            "数据库连接池初始化完成 max_connections={n}",
            "数据库写入完成 table={db_table} 影响行数={n}",
            "数据库事务提交成功 transaction_id={uuid}",
            "数据库索引重建完成 table={db_table} 耗时={duration}ms",
        ],
        "WARNING": [
            "数据库慢查询 table={db_table} 耗时={query_time}ms 超过阈值",
            "数据库连接池使用率 {n}% 可用连接={n}",
            "数据库死锁检测 table={db_table} 自动回滚并重试",
        ],
        "ERROR": [
            "数据库连接失败: {error_msg}",
            "数据库查询异常 table={db_table} 错误: {error_msg}",
            "数据库连接池耗尽: 无可用连接 max_connections={n}",
            "数据库事务回滚 transaction_id={uuid} 原因: {error_msg}",
        ],
    },

    # ========================================================================
    # app.services.cache - 缓存服务
    # ========================================================================
    "app.services.cache": {
        "INFO": [
            "缓存命中 key={cache_key} 命中率={n}%",
            "缓存写入成功 key={cache_key} ttl={n}s",
            "缓存预热完成 加载{n}条热点数据",
            "缓存失效标记 key={cache_key} 原因: 数据更新",
        ],
        "WARNING": [
            "缓存命中率下降 当前={n}% 低于阈值 50%",
            "缓存内存使用率 {n}% 接近上限",
            "缓存 key 过期过多 一次过期{n}条 key",
        ],
        "ERROR": [
            "缓存服务不可用: {error_msg}",
            "缓存反序列化失败 key={cache_key} 数据格式异常",
        ],
    },

    # ========================================================================
    # app.services.file_storage - 文件存储
    # ========================================================================
    "app.services.file_storage": {
        "INFO": [
            "文件上传完成 path={path} size={size} bytes",
            "文件下载开始 path={path} client_ip={ip}",
            "文件删除完成 path={path}",
            "文件复制完成 from={path} to={path}",
            "文件元数据更新 path={path}",
        ],
        "WARNING": [
            "存储空间使用率 {n}% 建议扩容",
            "文件下载速度较慢 path={path} 速度={n}KB/s",
            "文件即将过期 path={path} 剩余{n}天",
        ],
        "ERROR": [
            "文件不存在 path={path}",
            "文件读取失败 path={path} 错误: {error_msg}",
            "存储空间不足 剩余={n}MB 请求大小={size}MB",
            "文件上传中断 path={path} 已上传={size} bytes",
        ],
    },

    # ========================================================================
    # app.middleware.auth - 认证中间件
    # ========================================================================
    "app.middleware.auth": {
        "INFO": [
            "认证通过 user_id={user_id} method=jwt",
            "Token 刷新成功 user_id={user_id} 新过期时间={n}小时",
            "权限校验通过 user_id={user_id} 请求资源: {endpoint}",
            "会话创建成功 session_id={session_id} user_id={user_id}",
        ],
        "WARNING": [
            "Token 即将过期 user_id={user_id} 剩余有效时间={n}分钟",
            "登录尝试失败 user_id={user_id} 失败次数={n}",
            "权限不足 user_id={user_id} 请求资源: {endpoint}",
        ],
        "ERROR": [
            "认证失败 user_id={user_id} 原因: token_expired",
            "Token 验证异常: {error_msg}",
            "会话无效 session_id={session_id} 已过期或注销",
            "非授权访问尝试 ip={ip} endpoint={endpoint}",
        ],
    },

    # ========================================================================
    # app.middleware.rate_limiter - 限流中间件
    # ========================================================================
    "app.middleware.rate_limiter": {
        "INFO": [
            "限流检查通过 ip={ip} 当前QPS={n}",
            "限流配置更新 window_size={n}s max_requests={n}",
        ],
        "WARNING": [
            "IP 接近限流阈值 ip={ip} 当前QPS={n} 阈值={n}",
            "全局 QPS 偏高 当前={n} 建议扩容",
        ],
        "ERROR": [
            "IP 触发限流 ip={ip} 已被封锁{n}秒",
        ],
    },

    # ========================================================================
    # uvicorn / gunicorn - Web 服务器
    # ========================================================================
    "uvicorn.access": {
        "INFO": [
            '{ip} - - [{timestamp}] "{method} {endpoint} HTTP/1.1" {http_status} {size}',
            "Uvicorn running on http://{ip}:{n} (Press CTRL+C to quit)",
            "Started server process [{n}]",
            "Waiting for application startup.",
            "Application startup complete.",
        ],
        "WARNING": [
            '{ip} - - [{timestamp}] "{method} {endpoint} HTTP/1.1" 429 {size}',
            "Worker 进程重启 pid={n} 原因: 内存超限",
        ],
        "ERROR": [
            '{ip} - - [{timestamp}] "{method} {endpoint} HTTP/1.1" 500 {size}',
            "Worker 进程异常退出 pid={n}",
            "服务器启动失败 端口={n} 已被占用",
        ],
    },

    # ========================================================================
    # app.services.skill_loader - 技能加载器
    # ========================================================================
    "app.services.skill_loader": {
        "INFO": [
            "<skill-loaded name=\"{skill_name}\">",
            "技能资源文件就绪 path={path}",
            "技能执行完成 name={skill_name} 耗时={duration}ms",
            "技能列表刷新完成 已注册{n}个技能",
        ],
        "WARNING": [
            "技能版本不兼容 name={skill_name} 期望版本>=2.0",
            "技能加载耗时较长 name={skill_name} 耗时={duration}ms",
        ],
        "ERROR": [
            "技能加载失败 name={skill_name} 错误: {error_msg}",
            "技能执行异常 name={skill_name} 错误: {error_msg}",
            "技能资源文件缺失 name={skill_name} path={path}",
        ],
    },
}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def random_from_pool(pool: list[str]) -> str:
    """从池中随机选取一个值"""
    return random.choice(pool)


def all_modules() -> list[str]:
    """返回所有模块名"""
    return list(TEMPLATES.keys())


def get_levels_for_module(module: str) -> list[str]:
    """返回某模块支持的日志级别"""
    t = TEMPLATES.get(module)
    if not t:
        return []
    return list(t.keys())