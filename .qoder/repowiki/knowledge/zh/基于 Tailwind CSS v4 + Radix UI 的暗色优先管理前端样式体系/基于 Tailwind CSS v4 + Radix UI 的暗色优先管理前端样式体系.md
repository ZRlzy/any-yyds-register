---
kind: frontend_style
name: 基于 Tailwind CSS v4 + Radix UI 的暗色优先管理前端样式体系
category: frontend_style
scope:
    - '**'
source_files:
    - frontend/package.json
    - frontend/vite.config.ts
    - frontend/eslint.config.js
    - frontend/src/index.css
    - frontend/src/App.css
    - frontend/src/App.tsx
    - frontend/src/components/ui/button.tsx
    - frontend/src/components/ui/badge.tsx
    - frontend/src/components/ui/card.tsx
    - frontend/src/lib/utils.ts
---

## 1. 技术栈与工具
- 构建与开发：Vite（`vite.config.ts`），通过 `@tailwindcss/vite` 插件集成 Tailwind CSS v4，构建产物输出到根目录 `static/` 供后端静态服务。
- 框架：React 19 + TypeScript，路由使用 `react-router-dom`。
- 样式方案：Tailwind CSS v4（原子类）+ 自定义 CSS 变量（Design Tokens）+ 少量手写 CSS 模块（`index.css`、`App.css`）。
- 组件库：自研 `components/ui` 基础组件，基于 `class-variance-authority`（CVA）定义变体，配合 `@radix-ui/react-*` 无样式原子组件（Dialog、Dropdown、Select、Tabs、Toast、Slot）保证可访问性。
- 工具库：`clsx` + `tailwind-merge` 提供统一的 `cn()` 合并函数（`src/lib/utils.ts`），用于安全拼接动态 className。
- 图标：`lucide-react`。
- Lint：ESLint Flat Config（`eslint.config.js`），启用 `@eslint/js`、`typescript-eslint`、`react-hooks`、`react-refresh`。

## 2. 设计令牌（Design Tokens）
所有视觉语义集中在 `frontend/src/index.css` 的 `:root` 与 `.light` 伪类中，采用 CSS 自定义属性组织：
- 表面层：`--bg-base`、`--bg-surface`、`--bg-pane`、`--bg-card`、`--bg-input`、`--bg-hover`、`--chip-bg`
- 边框：`--border`、`--border-soft`
- 文本：`--text-primary`、`--text-secondary`、`--text-muted`、`--text-accent`
- 强调色：`--accent`、`--accent-strong`、`--accent-hover`、`--accent-rgb`、`--accent-soft`、`--accent-edge`、`--bg-active`、`--hero-bg`
- 阴影：`--shadow-soft`、`--shadow-hard`、`--surface-glow`
主题切换通过在 `<html>` 上添加/移除 `light` class 实现，默认暗色主题（`#09090b` 背景）。

## 3. 架构与约定
### 3.1 全局样式分层
- `index.css`：导入 Tailwind、声明 Design Tokens、全局 reset、对话框/表单/表格/进度条/滚动条/响应式等通用样式。
- `App.css`：仅保留 Vite 模板遗留样式（`.counter`、`.hero`、`#center`、`#next-steps` 等），业务页面不应新增此类全局样式。
- 组件级样式：全部通过 Tailwind 原子类 + CVA 变体完成，避免在组件内写独立 CSS 文件。

### 3.2 基础组件模式（`components/ui`）
- Button（`button.tsx`）：用 CVA 定义 `variant`（default/destructive/outline/ghost/link）和 `size`（default/sm/lg/icon），通过 `asChild` 透传至 Radix Slot。
- Badge（`badge.tsx`）：CVA 定义 default/success/warning/danger/secondary 五种语义变体。
- Card（`card.tsx`）：组合 `Card` / `CardHeader` / `CardTitle` / `CardContent`，统一使用 `rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4`。
- 所有组件统一通过 `cn(...)` 合并外部传入 className，确保覆盖优先级正确。

### 3.3 布局与导航
- `App.tsx` 实现侧边栏 + 主内容区的 Shell 布局，侧边栏支持折叠（状态持久化到 `localStorage('sidebar-collapsed')`）。
- 导航项集中为 `NAV_ITEMS` 常量，通过 `react-router-dom` 的 `NavLink` 高亮当前路由。
- 账号与设置菜单根据运行时平台列表动态展开。

### 3.4 主题与鉴权
- 主题状态由 `App` 组件维护，支持 `dark` / `light` / `system` 三种模式，通过监听 `prefers-color-scheme` 变化并同步到 `document.documentElement.classList`。
- 登录态通过 `localStorage('_auth_token')` 管理，`apiFetch` 自动注入 `Authorization: Bearer <token>` 请求头，401 时清空 token 并刷新页面。

## 4. 约定与约束
- **颜色必须走 CSS 变量**：组件样式中引用 `var(--accent)`、`var(--bg-card)`、`var(--border)` 等语义变量，禁止硬编码十六进制颜色值（除少数语义明确的 Tailwind 色如 `red-600` 用于 destructive 场景）。
- **组件样式通过 CVA + cn 管理**：所有可复用组件的样式变体必须用 `cva()` 声明并通过 `cn()` 合并，禁止在 JSX 中直接拼凑大量条件 className。
- **全局样式收敛于 `index.css`**：新增全局规则（表单、表格、对话框、滚动条等）应追加到 `index.css` 对应区块，而非新建 CSS 文件。
- **主题切换通过 class 切换**：新增主题相关样式需同时考虑 `.light` 下的变量覆盖，保持明暗双主题一致。
- **API 基址与环境变量**：通过 `import.meta.env.VITE_API_BASE` 配置，默认 `/api`，开发期由 Vite proxy 转发到 `http://localhost:8000`。
- **构建产物位置固定**：`vite.config.ts` 将构建输出写入 `../static`，因此前端样式变更会直接影响后端静态资源目录。
- **响应式断点**：项目使用 Tailwind 默认断点，并在 `index.css` 中针对 `1100px` 和 `720px` 做了额外适配（侧边栏堆叠、弹窗圆角缩小等）。