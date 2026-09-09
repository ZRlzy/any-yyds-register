---
kind: configuration_system
name: 基于 SQLite + Provider 动态定义的运行时配置系统
category: configuration_system
scope:
    - '**'
source_files:
    - core/config_store.py
    - infrastructure/config_repository.py
    - application/config.py
    - api/config.py
    - core/db.py
    - customer_portal_api/app/config.py
    - Dockerfile
    - docker-compose.yml
    - docker-entrypoint.sh
    - electron/main.js
    - platforms/chatgpt/constants.py
    - platforms/chatgpt/switch.py
    - platforms/cursor/switch.py
    - platforms/kiro/switch.py
    - platforms/trae/switch.py
    - tests/conftest.py
---

## 1. 总体方案

本仓库采用**三层配置模型**：
- **进程级环境变量**（`os.environ`）用于启动期不可变参数，如数据库连接、鉴权口令、平台 URL 等；
- **SQLite 持久化 key-value 配置表**（`configs` 表）用于用户通过 API 动态修改的运行时配置；
- **Provider 定义驱动的动态字段集**：配置键白名单由 `provider_definitions` 表中的 provider 字段描述动态生成，新增 provider 即自动暴露新的可配置项。

核心思想是“配置即数据”——所有可编辑的配置最终都落库为 `ConfigItem(key, value)` 记录，读取时按白名单过滤后以扁平 `dict[str, str]` 形式返回给前端。

## 2. 关键文件与职责

| 文件 | 职责 |
|---|---|
| `core/config_store.py` | 最小化的 SQLite key-value 存储抽象，提供 `get/set/get_all/set_many` |
| `infrastructure/config_repository.py` | 配置仓储层，维护 `BASE_KEYS` 白名单并合并 provider 动态字段，实现 `get_flat/update_flat` |
| `application/config.py` | 应用服务层，聚合 `ConfigRepository`、`ProviderDefinitionsService`、`ProviderSettingsService`、`PlatformsService`，对外暴露 `/api/config` 的业务语义 |
| `api/config.py` | FastAPI Router，暴露 `GET /config`、`PUT /config`、`GET /config/options` |
| `core/db.py` | 全局 SQLite 引擎初始化，`ACCOUNT_MANAGER_DATABASE_URL` 环境变量决定数据库位置（默认 `account_manager.db`） |
| `customer_portal_api/app/config.py` | 客户门户子服务的独立 Settings 类，全部从 `PORTAL_*` 环境变量加载 |
| `Dockerfile` / `docker-compose.yml` / `docker-entrypoint.sh` | 容器化部署时的环境变量注入点（`APP_PASSWORD`、`VNC_PASSWORD`、`DISPLAY`、`ACCOUNT_MANAGER_DATABASE_URL`） |
| `electron/main.js` | Electron 客户端启动内嵌后端时传递 `PORT=8000` 环境变量 |
| `platforms/*/constants.py`、`switch.py` 等 | 各平台插件通过 `os.environ.get(...)` 读取自身运行参数（如 `OPENAI_AUTH_BASE_URL`、`OAUTH_CLIENT_ID`、`XDG_CONFIG_HOME` 等） |

## 3. 架构与约定

### 3.1 配置键来源与白名单机制
`ConfigRepository.BASE_KEYS` 硬编码了系统级配置键（`default_executor`、`default_identity_provider`、`chrome_user_data_dir`、`cpa_api_url`、`team_manager_url`、`any2api_password` 等），并通过 `ProviderDefinitionsRepository.list_by_type(provider_type)` 遍历 mailbox/captcha/sms 三类 provider 的 `fields_json`，将每个 field 的 `key` 追加到允许写入集合中。因此：**新增 provider 或扩展其 fields 即自动增加可配置项，无需改代码**。写操作会过滤掉不在白名单中的键，读操作也仅返回白名单内的键。

### 3.2 配置分层顺序
- **启动期常量**：`main.py` 设置 `PYTHONUTF8=1`；`core/db.py` 通过 `ACCOUNT_MANAGER_DATABASE_URL` 选择 SQLite 路径；`api/auth.py`、`core/auth.py` 通过 `APP_PASSWORD` 控制鉴权开关。
- **运行时配置**：通过 `GET/PUT /api/config` 读写 SQLite 中的 `configs` 表，供前端“设置”页面管理。
- **Provider 实例配置**：通过 `provider_settings` 表（`ProviderSettingModel.config_json`）保存具体 provider 实例的认证凭据与参数，由 `ProviderSettingsService` 管理。
- **平台特定环境变量**：各 platform 插件直接 `os.environ.get(...)` 读取，不经过统一配置中心。

### 3.3 生命周期集成
FastAPI 的 `lifespan` 钩子在启动时依次执行：`init_db()` → `load_all()`（注册平台）→ `load_providers()`（注册 provider）→ scheduler/task_runtime/solver_manager/lifecycle_manager 启动。这意味着配置系统在数据库就绪后才开始工作，且 provider 定义在启动阶段完成发现。

### 3.4 多进程/多组件配置
- 主进程通过 `--solver` 参数切换为 Turnstile Solver 子进程模式（`services.turnstile_solver.start.main`）。
- Docker 入口脚本 `docker-entrypoint.sh` 先启动 Xvfb/x11vnc/noVNC，再 `exec uvicorn main:app`，确保 VNC 相关环境变量（`DISPLAY`、`VNC_PASSWORD`）在主进程前生效。
- Electron 客户端通过 `child_process.spawn` 拉起打包后的后端，并注入 `PORT=8000`。

## 4. 约定与约束

1. **所有可编辑配置必须通过 `/api/config` 接口写入**，禁止业务代码直接操作 `ConfigStore`（仓储层封装了白名单校验）。
2. **配置值统一以字符串存储**（`ConfigItem.value: str`），类型转换由调用方负责。
3. **敏感信息（密码、token）应存于 `provider_settings` 的 `auth_json` 而非通用 `configs` 表**，因为后者会被 `get_options()` 暴露给前端。
4. **新增 provider 时需在 definition 的 `fields_json` 中声明字段 key**，否则该字段不会出现在配置白名单中。
5. **数据库连接串必须通过 `ACCOUNT_MANAGER_DATABASE_URL` 环境变量传入**，默认回退到项目根目录下的 `account_manager.db`；测试环境通过 `conftest.py` 覆盖该变量指向临时 SQLite。
6. **生产部署必须设置 `APP_PASSWORD`**，否则鉴权中间件跳过认证（见 `core/auth.py` 与 `Dockerfile` 注释）。
7. **各平台插件的环境变量名不得随意变更**（如 `OPENAI_AUTH_BASE_URL`、`CHATGPT_APP_URL`、`OAUTH_CLIENT_ID`、`SENTINEL_*`、`XDG_CONFIG_HOME`、`LOCALAPPDATA` 等），这些被多个 platform 模块直接引用。
8. **客户门户子服务（`customer_portal_api`）完全独立**，使用自己的 `Settings` 类和 `PORTAL_*` 环境变量，不与主服务共享配置空间。

## 5. 适用性判断

该仓库存在完整的配置系统：统一的 SQLite 持久化、Provider 驱动的配置键白名单、环境变量注入、容器化部署支持以及前后端一致的 REST 配置接口，属于高置信度的已实现系统。