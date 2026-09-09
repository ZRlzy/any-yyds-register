---
kind: dependency_management
name: 多语言依赖管理：pip + npm/yarn + Docker 锁定策略
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
    - customer_portal_api/requirements.txt
    - frontend/package.json
    - frontend/package-lock.json
    - electron/package.json
    - electron/package-lock.json
    - Dockerfile
    - customer_portal_api/Dockerfile
    - .github/workflows/release.yml
    - CONTRIBUTING.md
---

## 1. 使用的系统与工具

本仓库采用**多语言、多子项目**的依赖管理方式，分别使用以下工具声明与安装依赖：

- **Python（主后端 & 客户门户）**：使用 `pip` + `requirements.txt` 作为依赖清单；通过 `.venv/` 虚拟环境隔离运行期依赖。
- **前端（React/Vite）**：使用 `npm`（`package.json` + `package-lock.json`）管理依赖。
- **Electron 桌面客户端**：使用 `npm`（`electron/package.json` + `electron/package-lock.json`）管理 Electron 及打包相关依赖。
- **容器化构建**：通过 `Dockerfile` 与 `docker-compose.yml` 在镜像中执行 `pip install -r requirements.txt` 安装 Python 依赖。

未发现使用 `poetry`、`Pipenv`、`pyproject.toml`、`setup.py`、Go `go.mod`、`vendor/` 等替代方案。所有 Python 依赖均集中声明于根级 `requirements.txt`，并通过相对引用被子模块复用。

## 2. 关键文件

| 作用 | 文件路径 | 说明 |
|---|---|---|
| 主后端 Python 依赖清单 | `requirements.txt` | 声明 FastAPI、Playwright、Pydantic v2、Camoufox、Quart、PyInstaller 等运行时与测试依赖 |
| 客户门户 Python 依赖清单 | `customer_portal_api/requirements.txt` | 仅一行 `-r ../requirements.txt`，复用根依赖清单 |
| 前端依赖清单 | `frontend/package.json` | React 19、Tailwind CSS v4、Vite 8、TypeScript ~5.9 等 |
| 前端锁文件 | `frontend/package-lock.json` | 锁定 npm 依赖树（lockfileVersion 3），已提交至仓库 |
| Electron 依赖清单 | `electron/package.json` | Electron ^33、electron-builder ^25、electron-updater ^6 |
| Electron 锁文件 | `electron/package-lock.json` | 锁定 Electron 生态依赖树 |
| 容器构建脚本 | `Dockerfile` | `COPY requirements.txt` → `RUN pip install --no-cache-dir -r requirements.txt` |
| 客户门户容器构建 | `customer_portal_api/Dockerfile` | 同时复制并安装根与子目录的 `requirements.txt` |
| CI/CD 安装入口 | `.github/workflows/release.yml` | 在 release 流程中执行 `pip install -r requirements.txt` |
| 本地开发指引 | `CONTRIBUTING.md`、`README*.md` | 统一以 `pip install -r requirements.txt` 作为安装命令 |

## 3. 架构与约定

### 3.1 Python 依赖管理

- **单一事实来源**：所有 Python 依赖集中在根 `requirements.txt`，按“运行时依赖”和“Testing”两个逻辑段组织（通过注释分隔）。`customer_portal_api/requirements.txt` 通过 `-r ../requirements.txt` 引用根清单，避免重复维护。
- **版本约束风格**：全部使用 `>=X.Y.Z` 形式的**最小版本下限**，不固定精确版本，也不使用 `~=` 或 `==`。例如 `fastapi>=0.110.0`、`playwright>=1.43.0`、`pytest>=8.0.0`。
- **虚拟环境**：根目录存在 `.venv/`，表明开发者使用 `python -m venv .venv` 创建隔离环境；`.gitignore` 应忽略该目录（未在本仓库提交实际包内容）。
- **无 vendoring**：未发现 `vendor/`、`third_party/` 或任何第三方源码内联拷贝。

### 3.2 Node.js 依赖管理

- **前端与 Electron 各自独立**：`frontend/` 与 `electron/` 各有独立的 `package.json`，互不共享依赖，体现“应用层与桌面壳层解耦”。
- **锁文件提交**：`frontend/package-lock.json` 与 `electron/package-lock.json` 均已纳入版本控制，确保构建可重现。
- **私有源/代理**：从锁文件中可见 `resolved` 字段指向 `https://registry.npmmirror.com/...`，表明当前环境配置了国内 npm 镜像源（如 `.npmrc` 或全局配置），但仓库本身未包含 `.npmrc` 文件。

### 3.3 容器化与 CI 集成

- `Dockerfile` 将 `requirements.txt` 复制到镜像后执行 `pip install --no-cache-dir -r requirements.txt`，保证镜像内依赖与源码一致。
- `customer_portal_api/Dockerfile` 同时复制根依赖与子模块依赖，并分别安装，保持服务边界清晰。
- `.github/workflows/release.yml` 在发布流水线中同样通过 `pip install -r requirements.txt` 安装依赖，形成“源码 → 锁文件/清单 → 容器/CI”的一致性链路。

## 4. 约定与约束

- **Python 依赖必须通过 `requirements.txt` 声明**：所有文档（`README.md`、`README_en.md`、`README_vi.md`、`CONTRIBUTING.md`）以及 CI 工作流、Dockerfile 均统一使用 `pip install -r requirements.txt` 作为安装入口，未见其他安装方式。
- **新增 Python 依赖需添加到根 `requirements.txt`**：由于 `customer_portal_api/requirements.txt` 通过 `-r ../requirements.txt` 引用根清单，新增依赖应直接修改根清单，而非子模块清单。
- **Python 不使用精确版本锁定**：清单中未出现 `==` 或 `pip freeze` 生成的绝对版本锁定；若需锁定，应配合 `pip-tools` / `pip-compile` 或 `poetry lock` 等工具生成额外锁文件（目前仓库未提供）。
- **Node 依赖必须提交 `package-lock.json`**：前后端均已提交锁文件，新增依赖后应同步更新对应 lock 文件以保证构建可重现。
- **无私有 PyPI 源或 `pip.conf` 配置**：未发现 `pip.conf`、`setup.cfg` 中的 `index-url`、`GITHUB_TOKEN`、`PIP_INDEX_URL` 等私有源配置，依赖均来自官方 PyPI。
- **无 Go/Rust/Java 等其他语言依赖**：仓库未包含 `go.mod`、`Cargo.toml`、`pom.xml` 等，因此本仓库的依赖管理范围仅限于 Python 与 Node.js 两类。

## 5. 风险与改进建议（基于现状观察）

- Python 依赖仅用 `>=` 下限，缺少确定性锁定，可能导致不同环境安装到不同次/补丁版本；建议引入 `pip-compile` 生成 `requirements.lock` 或在 CI 中校验依赖变更。
- 前端与 Electron 的 `package-lock.json` 已提交，但仓库未包含 `.npmrc`，若团队切换 npm 源可能产生差异；建议在仓库内显式声明 registry。
- 未发现 `pyproject.toml` 或 `setup.py`，无法利用现代 Python 项目的元数据与构建系统能力（如 `build-system`、`tool.poetry` 等）。