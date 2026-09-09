---
kind: error_handling
name: FastAPI HTTP 异常与注册领域异常体系
category: error_handling
scope:
    - '**'
source_files:
    - core/registration/errors.py
    - core/auth.py
    - main.py
    - api/accounts.py
    - api/sms.py
    - api/provider_settings.py
    - api/provider_definitions.py
    - api/proxies.py
    - api/account_checks.py
    - api/actions.py
    - core/registration/flows.py
    - services/task_runtime.py
---

## 1. 整体方案

本项目采用 **分层错误处理**：
- **HTTP 层**（`api/`）统一通过 FastAPI 的 `HTTPException` 返回业务错误，由 FastAPI 自动序列化为 JSON。
- **领域/流程层**（`core/registration/errors.py`）定义注册流程专用的 Python 异常类型，用于在浏览器/协议注册流程内部传递结构化错误。
- **中间件层**（`core/auth.py`）提供基于 `BaseHTTPMiddleware` 的鉴权拦截，对未认证请求直接返回 401。
- **进程/IO 层**（`main.py`）在启动阶段强制 stdout/stderr 使用 UTF-8 并设置 `errors="replace"`，避免 Windows 下非 GBK 字符导致进程崩溃。

项目没有自定义全局异常处理器（`@app.exception_handler`），也没有统一的 `ExceptionMiddleware`，因此各路由自行决定如何把异常转换为 HTTP 响应。

## 2. 关键文件与位置

| 文件 | 职责 |
|---|---|
| `core/registration/errors.py` | 注册领域异常基类 `RegistrationError(RuntimeError)` 及其子类：`IdentityResolutionError`、`CaptchaConfigurationError`、`OtpTimeoutError`、`BrowserReuseRequiredError`、`RegistrationUnsupportedError` |
| `core/auth.py` | `AuthMiddleware`，实现 Bearer Token / Cookie 鉴权，公开路径 `/api/health`、`/api/ready`、`/api/auth/*` 免鉴权 |
| `main.py` | FastAPI 应用入口，挂载 `AuthMiddleware` 与 CORS，统一 `lifespan` 生命周期 |
| `api/accounts.py` | 账号导出等接口中捕获 `ValueError` 并转为 `HTTPException(400, ...)` |
| `api/sms.py` | 第三方短信 Provider 调用被 `try/except Exception` 包裹，失败时统一转 `HTTPException(502, str(exc))`；缺失 API Key 时返回 `400` |
| `api/provider_settings.py`、`api/provider_definitions.py`、`api/proxies.py`、`api/account_checks.py` | 同样以 `HTTPException(400/404)` 表达参数校验失败、资源不存在等场景 |
| `core/registration/flows.py` | `BrowserRegistrationFlow`、`ProtocolMailboxFlow`、`ProtocolOAuthFlow` 在流程内 raise `RuntimeError`（如“未实现浏览器注册适配器”）或依赖 helper 抛出自定义错误 |

## 3. 架构与约定

### 3.1 HTTP 层错误映射
- **参数/配置错误** → `HTTPException(400, "...")`。例如 `accounts.py` 中批量导出接口捕获 `ValueError` 后抛出 400；`sms.py` 在未配置 HeroSMS/SMSBower API Key 时直接返回 400。
- **资源不存在** → `HTTPException(404, "...中文消息...")`。如 `get_account`、`update_account`、`delete_account`、`proxies.py`、`provider_settings.py` 中均用此模式。
- **下游服务异常** → `HTTPException(502, str(exc))`。`api/sms.py` 对所有外部短信 Provider 调用使用 `try/except Exception` 包裹，失败统一返回 502。
- **任务创建失败** → `HTTPException(400, "任务创建失败")`（`api/actions.py`）。

### 3.2 领域异常体系
`core/registration/errors.py` 定义了以 `RegistrationError(RuntimeError)` 为根的异常族，语义清晰覆盖身份解析、验证码配置、OTP 超时、无头 OAuth 浏览器复用、平台不支持等注册阶段特有错误。这些异常目前仅作为领域层的错误载体，尚未在 API 层被统一捕获转换——当前 API 层主要捕获 `ValueError` 和 `Exception`。

### 3.3 鉴权中间件
`AuthMiddleware` 继承 `starlette.middleware.base.BaseHTTPMiddleware`，在 `dispatch` 中按以下顺序判断：
1. 若环境变量 `APP_PASSWORD` 为空，放行所有请求。
2. 匹配白名单前缀 `/api/health`、`/api/ready`、`/api/auth/` 放行。
3. 非 `/api` 开头的静态资源放行。
4. 检查 `Authorization: Bearer <password>` 或 Cookie `_auth=<password>`。
5. 不满足则返回 `Response(content='{"detail":"Unauthorized"}', status_code=401, media_type="application/json")`。

### 3.4 进程级健壮性
`main.py` 启动时强制 `sys.stdout`/`sys.stderr` 使用 UTF-8 编码，并以 `errors="replace"` 兜底，同时设置 `PYTHONUTF8=1` 环境变量，确保子进程也使用 UTF-8。这是针对 PyInstaller 打包 + Windows 中文环境下的防崩溃措施。

### 3.5 任务执行容错
`services/task_runtime.py` 的 `_run_task` 使用 `try/finally` 确保无论任务成功还是异常，worker 线程都会从 `_workers` 字典中移除，防止 worker 泄漏。任务执行本身委托给 `execute_task(task_id)`，异常由上层调度逻辑处理。

## 4. 约定与约束

- **API 层禁止裸 `raise Exception`**：除 `api/sms.py` 中对第三方短信 Provider 的 `except Exception` 外，其余路由均显式构造 `HTTPException`，保证对外响应格式一致。
- **业务校验错误统一走 `ValueError` → 400**：`accounts.py` 中多个导出端点捕获 `ValueError` 后转为 `HTTPException(400, str(exc)) from exc`，形成“参数/选择校验失败即 400”的约定。
- **下游不可用统一 502**：`api/sms.py` 将所有外部短信服务的异常包装为 502，区分客户端错误与服务端故障。
- **鉴权失败固定 401 JSON**：`AuthMiddleware` 返回固定格式的 `{"detail":"Unauthorized"}`，前端可据此提示登录。
- **注册流程错误使用领域异常**：`core/registration/errors.py` 中的异常类型应优先于通用 `RuntimeError`/`Exception`，便于后续在更高层统一捕获并转换为业务友好的错误码。
- **无全局异常处理器**：当前仓库未注册 `@app.exception_handler`，新增 HTTP 错误语义需在各路由处显式 `raise HTTPException(...)`，这是当前代码库的实际约束而非文档化规范。

## 5. 适用性说明

该错误处理体系适用于本仓库的 FastAPI 后端与自动化注册流程，覆盖了 HTTP 响应、鉴权中间件、领域异常以及进程级 IO 健壮性四个层面。