# Log MCP 服务升级记录（2026-08-10）

## 背景

原 log MCP（`E:\weekAgent\log_generator\`）只有 2 个 resources，存在限制：
- 单次读取最多 500 行，且从文件**开头**读（docstring 写"末尾"但实现是 offset=0）
- 无分页、无目录浏览、无筛选统计
- 锁死在 `generated_logs` 单个目录

用户需求：目录浏览 + 指定目录/文件读取 + 增量读取 + 定时任务 + LLM 全文分析。

## 变更内容

### 1. config.py
- 新增 `ALLOWED_ROOTS`：白名单根目录（默认 `generated_logs` + `log_files`），
  支持 `LOG_GEN_ROOTS` 环境变量分号分隔覆盖，自动去重、过滤不存在的目录
- 新增 `MCP_READ_MAX_BYTES`（默认 500KB 响应体上限）

### 2. engine.py（新增 LogDataAccess 数据访问层）
- `resolve_path` / `_find_root`：多根目录相对路径解析 + 路径穿越防护
- `list_roots` / `list_dir`：目录浏览
- `file_info`：行数/大小/mtime（增量计算关键）
- `read_file`：分页读取，**带行号**，支持 offset 游标 + max_bytes 截断
- `head` / `tail` / `sample`（head/tail/random/evenly）/ `extract`（级别+正则）/ `stats`
- 原有 `LogGenerator` 生成功能未动

### 3. mcp_server.py（重写，备份 .bak）
- 保留 resources（`log://files`、`log://{path}`）兼容旧客户端
- 新增 10 个 tools：list_roots / list_dir / list_files / file_info /
  read_file / head / tail / sample / extract / stats

### 4. cursor_manager.py（新增）
- 游标状态机：`cursor.json` 记录每个文件的已分析行数
- `compute_increments`：新文件(new) / 增量(increment) / 截断重置(reset) / 删除标记(deleted)
- 内置 demo 自测

### 5. incremental_runner.py（新增）
- cron 定时增量入口：扫描 → 计算增量 → 落盘 → 更新游标
- 参数：`--cursor` / `--out` / `--dry-run` / `--max-lines`

### 6. skills/log-analysis/SKILL.md
- 新增 Step 0.5「数据源选择（local / MCP）」
- MCP 工具清单表 + 路径规则
- 大文件读取策略（上下文保护）
- 增量监控模式工作流（cron 示例）
- MCP 服务启动命令

## 测试结果（全部通过）

| 测试项 | 结果 |
|--------|------|
| config 根目录加载（2 个） | ✅ |
| list_roots / list_dir（含 mms 子目录） | ✅ |
| file_info（2394 行） | ✅ |
| head / tail / sample / extract / stats | ✅ |
| read_file 分页 offset=100 | ✅ |
| 路径穿越防护（4 种恶意路径） | ✅ 全部拦截 |
| cursor_manager 单元自测（new/increment/reset/deleted） | ✅ |
| incremental_runner 首次运行（9 文件全量落盘） | ✅ |
| incremental_runner 二次运行（0 增量跳过） | ✅ |
| 模拟追加 2 行 → 增量发现（2394~2396） | ✅ |
| MCP HTTP 端到端（initialize + tools/list = 10 工具） | ✅ |
| 旧 resource 通道兼容（log://files） | ✅ |

## 服务状态

- 当前运行：PID 12580，`http://0.0.0.0:8899`（streamable-http）
- 启动命令：
  ```
  cd E:\weekAgent\log_generator
  E:\weekAgent\venv\Scripts\python.exe mcp_entry.py --transport streamable-http --port 8899
  ```
- 日志：`E:\weekAgent\log_generator\mcp_server.log`

## 2026-08-10 补充变更

1. **递归扫描**：`incremental_runner.py` 的 glob 改为 rglob（覆盖 mms 子目录），
   `mcp_server.py::list_files` 增加 `recursive` 参数（默认 False）
2. **BUG 修复（重要）**：增量超限截断时，游标错误地推进到 `inc["end"]`（文件总行数），
   导致未读取的中间段永久丢失（如 business.log 33 万行只读了前 200 行）
   → 改为只推进到实际读取的行数 `inc["start"] + delta`，截断时在落盘文件附加统计提示，
   剩余部分下轮继续读取。已用 500 行测试文件验证 200→400→500 分页完整消费。
3. **cron 定时任务已创建**：`af1c6c53-730e-4e67-96dc-128637e32b1d`（日志增量分析，
   每 30 分钟，silent，timeout 600s），已闭环测试通过（09:51 success；09:55 捕获真实增量并告警）

## 后续可选

- 定时任务创建：`qwenpaw cron create --agent-id log-agent --type agent --schedule-type cron --cron "*/30 * * * *" --name "日志增量分析" --channel console --target-user default --target-session <session_id> --timeout 600 --silent --text "执行日志增量分析任务"`
- 增量文件保留策略（inc/ 目录定期清理旧批次）

## 2026-08-10 体检建议落地（10:57）

1. **incremental_runner.py 新增 `--keep-batches N`**：落盘目录只保留最近 N 批增量文件
   （按文件名时间戳前缀分组，N<=0 不清理），解决 inc/ 长期积累问题。
   已验证：12 批 → 保留 10 批 → 删 2 批 ✅
2. **游标重置补读**：检测到 16 个文件游标为 BUG 时期"假全量"（游标>=实际行数 且
   实际行数>200），已重置为 0，cron 分批补读。手动跑一次验证：12 个大文件统一
   推进到 2000 行，小文件全部读完；business.log 剩余 33.6 万行按每 30 分钟 2000 行
   约 3.5 天补完。
3. **cron 任务更新**：`--max-lines 200 → 2000`（提速 10 倍），追加 `--keep-batches 10`，
   任务已启用（enabled=true）。下次整半点自动触发补读。
4. **清理**：删除测试残留 test_overflow.log（源文件+游标+3 个 inc 落盘）、工作区冗余
   （result.json / chat_dump.json / 2 份过时调研笔记，其余临时文件此前已清）。
5. **进程清理**：杀掉残留重复进程 PID 29380（保留 8899 端口监听者 12580）。

## 遗留待办

- `mcp_server.log` 目前仅 1.5KB，暂不需轮转；若长期运行建议加 RotatingFileHandler
  （超过 5MB 自动归档）。
