---
kind: logging_system
name: 基于 Python logging + 任务事件持久化的双轨日志系统
category: logging_system
scope:
    - '**'
source_files:
    - main.py
    - application/tasks.py
    - domain/task_logs.py
    - infrastructure/task_logs_repository.py
    - core/lifecycle.py
    - core/http_client.py
    - services/turnstile_solver/start.py
---

## 1. 使用的系统与框架

本仓库采用 **Python 标准库 `logging`** 作为进程级控制台日志输出，同时通过自研的 **任务事件（TaskEvent）持久化机制** 实现结构化、可查询的任务运行日志。两者并行存在：

- 进程/模块级日志：每个模块通过 `logger = logging.getLogger(__name__)` 创建 logger，使用 `logger.info / warning / error` 等标准级别输出到 stdout/stderr。
- 任务级日志：通过 `application/tasks.py` 中的 `TaskLogger` 与 `append_task_event`，将每条任务执行消息写入数据库 `TaskEventModel`，并同步 `print` 到控制台。

没有引入第三方日志框架（如 loguru、structlog），也没有集中式 `logging.config` 或文件 sink；所有进程日志最终由 uvicorn 直接输出到容器/终端 stdout/stderr。

## 2. 关键文件与包

| 职责 | 关键文件 |
|---|---|
| 应用入口与进程编码处理 | `main.py` |
| 任务执行与任务日志核心 | `application/tasks.py`（`TaskLogger`、`append_task_event`） |
| 任务日志领域模型 | `domain/task_logs.py`（`TaskLogRecord`） |
| 任务日志仓储（只读） | `infrastructure/task_logs_repository.py` |
| 生命周期后台任务日志 | `core/lifecycle.py` |
| HTTP 客户端重试/错误日志 | `core/http_client.py` |
| 各平台插件内部日志 | `platforms/*/` 下的模块（如 `chatgpt/register.py`、`chatgpt/payment.py`） |
| Turnstile Solver 子进程启动 | `services/turnstile_solver/start.py` |

## 3. 架构与设计约定

### 3.1 进程级日志（`logging`）

- 每个模块独立 `import logging` 并通过 `getLogger(__name__)` 获取命名 logger，遵循 Python 标准命名空间约定。
- 日志级别使用标准级别：`info` 用于常规流程，`warning` 用于非致命异常（如 HTTP 4xx/5xx、请求失败重试），`error` 用于明确错误路径。
- `main.py` 在启动时强制把 `sys.stdout` / `sys.stderr` 重配置为 UTF-8（设置 `PYTHONUTF8=1`，必要时用 `io.TextIOWrapper` 包装），确保 Windows 环境下中文/符号不会抛出 `UnicodeEncodeError`。
- 未对 `logging` 做全局 handler 配置——依赖 uvicorn 默认行为输出到控制台，适合 Docker/容器环境。

### 3.2 任务级结构化日志（TaskEvent）

`application/tasks.py` 是任务日志系统的核心：

- `append_task_event(task_id, message, *, event_type="log", level="info", detail=None)` 将一条事件写入 `TaskEventModel`，字段包括 `task_id`、`type`、`level`、`message`、`detail_json`。
- `TaskLogger` 封装了面向任务的生命周期日志：`mark_running()`、`finish(status, ...)`、`record_success()`、`record_error(error)`、`set_progress(...)`、`add_cashier_url(...)`、`set_result_data(...)`。
- 每条 `TaskLogger.log` 调用会同时 `print(f"[task:{self.task_id}] {message}")`，保证控制台可见。
- 事件类型分为两类：`event_type="log"` 表示普通日志行，`event_type="state"` 表示状态变更（如任务开始、结束、取消），便于前端区分渲染。
- 平台插件可通过 `platform.set_logger(logger.log)` 或 `platform._log_fn = logger.log` 注入任务日志句柄，使平台内部注册流程也能产出可追踪的事件。

### 3.3 日志数据模型

- 领域层 `domain/task_logs.TaskLogRecord` 定义只读记录结构：`id`、`platform`、`email`、`status`、`error`、`detail`、`created_at`。
- 基础设施层 `infrastructure/task_logs_repository.TaskLogsRepository.list(...)` 从 SQLModel 的 `TaskLog` 表分页读取，并将 `detail_json` 反序列化为 dict。
- 应用层 `application/task_logs.TaskLogsService` 提供 API 适配，过滤 `platform`、分页返回。

### 3.4 后台任务的日志模式

`core/lifecycle.py` 中的 `check_accounts_validity`、`refresh_expiring_tokens`、`flag_expiring_trials`、`refresh_and_sync_cpa` 等定时任务统一接受可选 `log_fn` 参数，默认回退到模块级 `logger.info`，便于测试注入自定义收集器。

## 4. 约定与约束

- **模块级日志必须使用 `logging.getLogger(__name__)`**：仓库中所有使用 `logging` 的模块均遵循此模式，未见直接使用 `logging.info()` 等根 logger 的情况。
- **任务日志必须通过 `TaskLogger` 或 `append_task_event`**：业务任务（注册、检测、CPA 同步等）不直接写数据库，而是经 `TaskLogger` 统一落库，保证事件具备 `task_id`、`level`、`event_type`、`detail` 等结构化字段。
- **事件类型约定**：`event_type="log"` 用于过程性消息，`event_type="state"` 用于任务状态切换（running、failed、cancelled、interrupted 等）。
- **日志级别约定**：正常流程用 `info`，可恢复异常/重试用 `warning`，不可恢复错误用 `error`；`TaskLogger.finish` 会根据最终状态自动选择 `error`/`warning`/`info`。
- **无文件/滚动日志 sink**：仓库未配置任何 `FileHandler`、`RotatingFileHandler` 或外部日志服务集成；生产部署应依赖容器编排（stdout/stderr 采集）。
- **跨进程日志隔离**：Turnstile Solver 作为独立子进程（`--solver` 模式）运行，拥有独立的 Quart 应用和日志流，不与主 FastAPI 共享 logger 实例。
- **HTTP 客户端统一错误日志**：`core/http_client.HTTPClient.request` 对所有 4xx/5xx 及连接异常统一以 `logger.warning` 记录，包含方法、URL、尝试次数，并在耗尽重试后抛出 `HTTPClientError`。
- **平台插件日志注入**：通过 `platform.set_logger(logger.log)` 或 `_log_fn` 属性注入任务日志回调，使平台内部步骤（如浏览器操作、API 调用）能产生带 `task_id` 的可追踪日志。