---
kind: build_system
name: 多阶段构建与跨平台发布流水线（Docker / PyInstaller / Electron Builder / GitHub Actions）
category: build_system
scope:
    - '**'
source_files:
    - Dockerfile
    - docker-compose.yml
    - docker-entrypoint.sh
    - .github/workflows/release.yml
    - requirements.txt
    - core/version.py
    - electron/package.json
    - electron/build-backend.sh
    - frontend/package.json
---

## 1. 构建系统概览

本项目采用**多工具链组合**的构建体系：
- **Python 后端**：基于 `requirements.txt` 管理依赖，使用 `uvicorn` 运行 FastAPI；通过 `PyInstaller` 打包为单文件可执行程序供 Electron 桌面端内嵌。
- **前端**：基于 Vite + React + TypeScript，独立 `frontend/package.json` 管理依赖，构建产物输出到 `static/`。
- **容器化**：多阶段 Dockerfile，第一阶段用 Node 20 构建前端，第二阶段用 Python 3.12 安装运行时依赖并注入静态资源。
- **桌面客户端**：Electron 应用通过 `electron-builder` 打包 macOS、Windows、Linux 三平台安装包。
- **CI/CD**：GitHub Actions `.github/workflows/release.yml` 在推送 `v*` tag 时触发并行构建 macOS、Windows、Docker 镜像，并最终创建 GitHub Release。

## 2. 关键构建文件

- `Dockerfile`：多阶段构建，安装 Chromium/XvFB/noVNC/camoufox 等浏览器运行时依赖，通过 `APP_VERSION` 构建参数注入版本。
- `docker-compose.yml`：本地开发编排，暴露 8000（FastAPI）、6080（noVNC）、8889（Turnstile Solver），挂载 `./data` 持久化 SQLite。
- `docker-entrypoint.sh`：启动 Xvfb → x11vnc → noVNC → uvicorn 的完整进程链。
- `requirements.txt`：声明式 Python 依赖，包含 fastapi、playwright、camoufox、quart、pyinstaller 等。
- `core/version.py`：版本占位文件，CI 构建时覆写 `__version__` 字段。
- `electron/package.json`：定义 `build:mac/win/linux/all` 脚本，使用 electron-builder 多平台打包。
- `electron/build-backend.sh`：调用 PyInstaller 将后端打包为单文件可执行，输出至 `electron/backend/backend/backend`。
- `.github/workflows/release.yml`：触发条件为 `push.tags: v*`，分三个 job 并行构建 mac/win/docker，最后合并 artifacts 创建 release。

## 3. 架构与约定

### 3.1 版本管理策略
- 版本号来源于 Git tag（如 `v1.2.3`），CI 中通过 `${GITHUB_REF_NAME#v}` 提取纯版本号。
- 版本同时注入三处：`core/version.py`（Python 运行时读取）、`electron/package.json`（npm version 命令更新）、Docker image tag（`ghcr.io/<repo>:<version>` 与 `latest`）。
- 本地开发默认版本为 `dev`，由 `core/version.py` 初始值提供。

### 3.2 前端构建流程
- 构建命令：`cd frontend && npm ci --legacy-peer-deps && npm run build`（CI 强制使用 `--legacy-peer-deps` 解决 peer dependency 冲突）。
- 构建产物为静态资源，被复制到 `static/` 目录，由 FastAPI 直接 serving。
- 本地开发通过 `vite dev` 启动热重载。

### 3.3 Python 后端打包
- **容器部署**：`pip install -r requirements.txt` 后 `playwright install chromium` + `python -m camoufox fetch` 安装浏览器。
- **桌面端嵌入**：`electron/build-backend.sh` 使用 PyInstaller `--onefile` 打包，显式 `--add-data` 所有子包（platforms/core/api/services/providers/application/infrastructure/domain/static），并通过 `--collect-all` 收集 quart、patchright、camoufox、browserforge 等动态导入模块。
- CI 中的 PyInstaller 命令与本地脚本基本一致，但 Windows 下使用 `pwsh` shell 且路径分隔符为分号。

### 3.4 浏览器与可视化环境
- Docker 镜像预装 Chromium/chromium-driver、Xvfb、x11vnc、noVNC/websockify，使无头浏览器可在容器中运行并通过 VNC 远程查看。
- `docker-entrypoint.sh` 按顺序启动 Xvfb (:99)、x11vnc（可选密码保护）、noVNC（端口 6080 映射到 5900）、最终 exec uvicorn。
- Playwright/Camoufox 浏览器二进制分别安装在 `/ms-playwright` 和 Python 包管理器缓存中。

### 3.5 CI 流水线设计
- 触发条件：仅对 `v*` 标签触发，避免每次 push 都构建。
- 并行 Job：`build-mac` (macos-latest)、`build-win` (windows-latest)、`build-docker` (ubuntu-latest) 三者互不依赖。
- 镜像缓存：Docker 构建使用 `type=gha` 的 cache-from/cache-to 加速。
- 镜像推送：登录 GHCR (`ghcr.io`)，推送 `latest` 与 `<version>` 双标签。
- 发布：`release` job 依赖上述三个 job，下载 artifacts 后调用 `softprops/action-gh-release` 创建 GitHub Release。
- Electron 签名：macOS 上使用 `codesign --force --deep --sign -` 进行 ad-hoc 签名以绕过 `xattr -cr` 问题。

## 4. 约定与约束

- **依赖锁定**：生产环境使用 `requirements.txt` 宽松版本约束（`>=`），未使用 `poetry.lock`/`pip-tools` 锁定具体版本。
- **Node 版本**：统一使用 Node 20（setup-node@v4 with node-version: 20）。
- **Python 版本**：统一使用 Python 3.12。
- **前端构建必须加 `--legacy-peer-deps`**：CI 中固定使用该参数，表明项目存在 peer dependency 冲突。
- **环境变量约定**：`APP_PASSWORD` 控制 API 访问密码，`VNC_PASSWORD` 控制 VNC 密码，`DISPLAY=:99` 指定虚拟显示，`ACCOUNT_MANAGER_DATABASE_URL` 指定 SQLite 数据库路径。
- **数据持久化**：通过 docker-compose 挂载 `./data:/app/data` 持久化 SQLite 数据库文件。
- **端口约定**：8000（FastAPI Web UI）、6080（noVNC）、8889（Turnstile Solver）。
- **镜像命名**：`ghcr.io/${{ github.repository }}:<version>` 与 `latest` 双标签。
- **Electron 镜像源**：通过 `ELECTRON_MIRROR` 和 `ELECTRON_BUILDER_BINARIES_MIRROR` 指向 npmmirror，适配国内网络环境。
- **Playwright 浏览器路径**：通过 `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` 环境变量集中管理浏览器安装位置。
- **测试**：使用 pytest + httpx，配置文件位于根目录 `pytest.ini`，测试用例集中在 `tests/` 目录。
- **客户门户服务**：独立的 `customer_portal_api/` 子服务，拥有自己的 `Dockerfile`、`docker-compose.yml`、`requirements.txt`，与主服务解耦部署。