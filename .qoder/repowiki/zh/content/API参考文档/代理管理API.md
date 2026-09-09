# 代理管理API

<cite>
**本文引用的文件**
- [api/proxies.py](file://api/proxies.py)
- [application/proxies.py](file://application/proxies.py)
- [domain/proxies.py](file://domain/proxies.py)
- [core/proxy_pool.py](file://core/proxy_pool.py)
- [core/proxy_providers.py](file://core/proxy_providers.py)
- [providers/proxy/api_extract.py](file://providers/proxy/api_extract.py)
- [providers/proxy/rotating_gateway.py](file://providers/proxy/rotating_gateway.py)
- [infrastructure/proxies_repository.py](file://infrastructure/proxies_repository.py)
- [core/db.py](file://core/db.py)
- [api/stats.py](file://api/stats.py)
</cite>

## 目录
1. [简介](#简介)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构总览](#架构总览)
5. [详细组件分析](#详细组件分析)
6. [依赖关系分析](#依赖关系分析)
7. [性能考量](#性能考量)
8. [故障排查指南](#故障排查指南)
9. [结论](#结论)
10. [附录：最佳实践与集成示例](#附录：最佳实践与集成示例)

## 简介
本文件面向“代理管理”相关能力，提供完整的 API 说明与实现细节。内容覆盖：
- 代理服务器配置与接入（HTTP、HTTPS、SOCKS5）
- 代理池管理（增删改查、批量导入、启用/禁用）
- 代理质量监控（可用性检测、成功率统计、自动切换策略）
- 负载均衡（按区域筛选、成功率加权轮询）
- 动态代理供应商集成（API 提取、旋转网关）
- 认证方式配置（用户名/密码嵌入 URL）
- 连接池与故障转移机制（连续失败自动禁用）
- 高可用代理池构建、网络性能优化、失效场景处理

## 项目结构
代理管理由四层构成：
- API 层：暴露 REST 接口（创建、批量导入、删除、切换、检测）
- 应用服务层：编排业务逻辑（序列化、触发异步检测）
- 领域模型层：定义数据契约（记录、命令、摘要）
- 基础设施层：数据库访问、代理池调度、动态代理提供者

```mermaid
graph TB
A["FastAPI Router<br/>/proxies"] --> B["ProxiesService<br/>应用服务"]
B --> C["ProxiesRepository<br/>数据访问"]
B --> D["ProxyPool<br/>调度与统计"]
D --> E["ProxyModel<br/>数据库表"]
D --> F["Dynamic Providers<br/>api_extract / rotating_gateway"]
F --> G["Provider Settings<br/>配置存储"]
```

图表来源
- [api/proxies.py:23-59](file://api/proxies.py#L23-L59)
- [application/proxies.py:10-48](file://application/proxies.py#L10-L48)
- [core/proxy_pool.py:9-90](file://core/proxy_pool.py#L9-L90)
- [core/db.py:291-300](file://core/db.py#L291-L300)
- [core/proxy_providers.py:77-102](file://core/proxy_providers.py#L77-L102)

章节来源
- [api/proxies.py:23-59](file://api/proxies.py#L23-L59)
- [application/proxies.py:10-48](file://application/proxies.py#L10-L48)
- [core/proxy_pool.py:9-90](file://core/proxy_pool.py#L9-L90)
- [core/db.py:291-300](file://core/db.py#L291-L300)
- [core/proxy_providers.py:77-102](file://core/proxy_providers.py#L77-L102)

## 核心组件
- ProxiesService：聚合仓库与代理池，负责序列化与任务触发
- ProxiesRepository：代理记录的 CRUD（含批量导入、启用/禁用）
- ProxyPool：获取下一个代理、上报成功/失败、全量健康检查
- 动态代理提供者：从第三方获取代理或固定网关旋转出口
- 数据库模型 ProxyModel：持久化代理元数据与质量指标

章节来源
- [application/proxies.py:10-48](file://application/proxies.py#L10-L48)
- [infrastructure/proxies_repository.py:21-72](file://infrastructure/proxies_repository.py#L21-L72)
- [core/proxy_pool.py:9-90](file://core/proxy_pool.py#L9-L90)
- [providers/proxy/api_extract.py:16-106](file://providers/proxy/api_extract.py#L16-L106)
- [providers/proxy/rotating_gateway.py:10-31](file://providers/proxy/rotating_gateway.py#L10-L31)
- [core/db.py:291-300](file://core/db.py#L291-L300)

## 架构总览
系统通过 FastAPI 暴露代理管理接口；请求进入服务层后，调用仓库进行数据操作，或通过代理池进行调度与健康检查。动态代理优先于静态池，未配置时回退到静态池。

```mermaid
sequenceDiagram
participant Client as "客户端"
participant API as "FastAPI /proxies"
participant Svc as "ProxiesService"
participant Repo as "ProxiesRepository"
participant Pool as "ProxyPool"
participant DB as "数据库(ProxyModel)"
participant Prov as "动态代理提供者"
Client->>API : POST /proxies/bulk
API->>Svc : bulk_create_proxies(...)
Svc->>Repo : bulk_create(urls, region)
Repo->>DB : INSERT 忽略重复
Repo-->>Svc : added 数量
Svc-->>API : {added}
API-->>Client : 200 OK
Client->>API : POST /proxies/check
API->>Svc : trigger_check()
Svc->>Pool : check_all() (后台线程)
Pool->>DB : SELECT 所有代理
loop 遍历代理
Pool->>Prov : get_proxy() (可选)
Prov-->>Pool : URL 或 None
alt 使用静态池
Pool->>DB : 读取活跃代理并排序
end
Pool->>DB : report_success/report_fail
end
Svc-->>API : {"message" : "检测任务已启动"}
API-->>Client : 200 OK
```

图表来源
- [api/proxies.py:23-59](file://api/proxies.py#L23-L59)
- [application/proxies.py:21-36](file://application/proxies.py#L21-L36)
- [core/proxy_pool.py:14-87](file://core/proxy_pool.py#L14-L87)
- [core/proxy_providers.py:77-102](file://core/proxy_providers.py#L77-L102)
- [core/db.py:291-300](file://core/db.py#L291-L300)

## 详细组件分析

### API 端点：代理管理
- GET /proxies
  - 功能：列出所有代理（包含状态、计数、最后检测时间）
  - 返回：代理列表
- POST /proxies
  - 功能：新增单个代理（支持 region）
  - 入参：url, region
  - 冲突：若 url 已存在返回错误
- POST /proxies/bulk
  - 功能：批量导入代理（去重、支持 region）
  - 入参：proxies[], region
  - 返回：{added: 数量}
- DELETE /proxies/{proxy_id}
  - 功能：删除代理
  - 返回：{ok: bool}
- PATCH /proxies/{proxy_id}/toggle
  - 功能：切换启用/禁用
  - 返回：{is_active: bool}
- POST /proxies/check
  - 功能：触发全量可用性检测（后台线程执行）
  - 返回：{"message": "检测任务已启动"}

章节来源
- [api/proxies.py:23-59](file://api/proxies.py#L23-L59)
- [application/proxies.py:14-36](file://application/proxies.py#L14-L36)

### 领域模型与数据契约
- ProxyRecord：代理记录（id, url, region, success_count, fail_count, is_active, last_checked）
- ProxyCreateCommand / ProxyBulkCreateCommand：创建命令
- ProxyCheckSummary：检测摘要（ok, fail）

章节来源
- [domain/proxies.py:8-35](file://domain/proxies.py#L8-L35)

### 代理池与调度算法
- 获取下一个代理优先级：
  1) 动态代理 provider（如已配置且启用）
  2) 静态代理池（数据库中的活跃代理）
- 静态池选择策略：
  - 可按 region 过滤
  - 按成功率加权排序（success_count / (success_count + fail_count)），再轮询选取
- 健康检查：
  - 对每个代理发起 HTTP 探测（超时控制）
  - 成功：success_count+1，last_checked=当前时间
  - 失败：fail_count+1，last_checked=当前时间；当连续失败达到阈值时自动禁用（is_active=False）
- 并发与锁：
  - 轮询索引使用线程锁保护
  - 健康检查在独立线程中执行

```mermaid
flowchart TD
Start(["开始"]) --> TryDyn["尝试动态代理"]
TryDyn --> DynOK{"是否获取到?"}
DynOK -- 是 --> ReturnDyn["返回动态代理URL"]
DynOK -- 否 --> LoadStatic["加载静态池(可按region过滤)"]
LoadStatic --> SortByRate["按成功率加权排序"]
SortByRate --> Pick["轮询取下一个"]
Pick --> ReturnStatic["返回静态代理URL"]
ReturnDyn --> End(["结束"])
ReturnStatic --> End
```

图表来源
- [core/proxy_pool.py:14-45](file://core/proxy_pool.py#L14-L45)

章节来源
- [core/proxy_pool.py:14-87](file://core/proxy_pool.py#L14-L87)

### 动态代理供应商集成
- api_extract：从 HTTP API 拉取代理列表（支持 JSON 或逐行文本），可附加协议与认证信息
  - 支持协议：http、https、socks5、socks4
  - 认证：username/password 会注入为 http://user:pass@host:port
- rotating_gateway：固定网关地址，每次请求由网关分配不同出口 IP
- 工厂与发现：
  - create_proxy_provider 根据 provider_key 创建具体实现
  - get_dynamic_proxy 从 ProviderSettingsRepository 读取启用的 proxy 设置，依次尝试各 provider，任一成功即返回

```mermaid
classDiagram
class BaseProxyProvider {
<<abstract>>
+get_proxy() Optional~string~
}
class ApiExtractProvider {
-api_url
-protocol
-username
-password
-timeout
+get_proxy() Optional~string~
}
class RotatingProxyProvider {
-gateway_url
+get_proxy() Optional~string~
}
BaseProxyProvider <|-- ApiExtractProvider
BaseProxyProvider <|-- RotatingProxyProvider
```

图表来源
- [core/proxy_providers.py:20-27](file://core/proxy_providers.py#L20-L27)
- [providers/proxy/api_extract.py:16-106](file://providers/proxy/api_extract.py#L16-L106)
- [providers/proxy/rotating_gateway.py:10-31](file://providers/proxy/rotating_gateway.py#L10-L31)

章节来源
- [core/proxy_providers.py:53-102](file://core/proxy_providers.py#L53-L102)
- [providers/proxy/api_extract.py:16-106](file://providers/proxy/api_extract.py#L16-L106)
- [providers/proxy/rotating_gateway.py:10-31](file://providers/proxy/rotating_gateway.py#L10-L31)

### 数据持久化与仓库
- ProxyModel：代理表字段包括 id、url（唯一）、region、success_count、fail_count、is_active、last_checked
- ProxiesRepository：
  - list：读取全部代理
  - create：插入前查重
  - bulk_create：批量插入，跳过空行与重复
  - delete：按 id 删除
  - toggle：切换 is_active

章节来源
- [core/db.py:291-300](file://core/db.py#L291-L300)
- [infrastructure/proxies_repository.py:21-72](file://infrastructure/proxies_repository.py#L21-L72)

### 统计与监控
- /stats/by-proxy：返回代理成功率排行（包含 success/fail/total/success_rate/is_active）
- 前端页面展示代理总数、启用数、成功次数、失败次数，并提供“检测全部”按钮触发后端检测

章节来源
- [api/stats.py:110-132](file://api/stats.py#L110-L132)
- [frontend/src/pages/Proxies.tsx:41-76](file://frontend/src/pages/Proxies.tsx#L41-L76)

## 依赖关系分析
- API 层依赖应用服务层
- 应用服务层依赖仓库与代理池
- 代理池依赖数据库模型与动态代理提供者
- 动态代理提供者依赖配置存储（ProviderSettingsRepository）

```mermaid
graph LR
API["api/proxies.py"] --> SVC["application/proxies.py"]
SVC --> REPO["infrastructure/proxies_repository.py"]
SVC --> POOL["core/proxy_pool.py"]
POOL --> DBM["core/db.py::ProxyModel"]
POOL --> PROV["core/proxy_providers.py"]
PROV --> EXT1["providers/proxy/api_extract.py"]
PROV --> EXT2["providers/proxy/rotating_gateway.py"]
```

图表来源
- [api/proxies.py:23-59](file://api/proxies.py#L23-L59)
- [application/proxies.py:10-48](file://application/proxies.py#L10-L48)
- [core/proxy_pool.py:9-90](file://core/proxy_pool.py#L9-L90)
- [core/proxy_providers.py:53-102](file://core/proxy_providers.py#L53-L102)

章节来源
- [api/proxies.py:23-59](file://api/proxies.py#L23-L59)
- [application/proxies.py:10-48](file://application/proxies.py#L10-L48)
- [core/proxy_pool.py:9-90](file://core/proxy_pool.py#L9-L90)
- [core/proxy_providers.py:53-102](file://core/proxy_providers.py#L53-L102)

## 性能考量
- 健康检查采用后台线程执行，避免阻塞请求
- 静态池按成功率加权排序，减少低质量代理的命中率
- 动态代理优先，降低本地池压力并提升多样性
- 批量导入去重，减少无效写入
- 建议：
  - 合理设置检测超时与频率，避免对上游造成压力
  - 对高频失败代理及时禁用，提高整体成功率
  - 结合 region 路由，就近选择代理以降低延迟

[本节为通用指导，不直接分析具体文件]

## 故障排查指南
- 新增代理返回“代理已存在”
  - 原因：url 重复
  - 处理：确认唯一性或改用批量导入（自动去重）
- 切换/删除返回不存在
  - 原因：proxy_id 无效
  - 处理：先查询列表确认 ID
- 检测无变化或失败率高
  - 检查动态代理配置是否正确启用
  - 查看 /stats/by-proxy 的 success_rate 与 is_active
  - 关注连续失败阈值导致的自动禁用行为
- 动态代理不可用
  - 检查提供商配置（API URL、网关地址、认证）
  - 查看日志中 provider 获取失败的调试信息

章节来源
- [api/proxies.py:28-59](file://api/proxies.py#L28-L59)
- [core/proxy_pool.py:56-87](file://core/proxy_pool.py#L56-L87)
- [api/stats.py:110-132](file://api/stats.py#L110-L132)

## 结论
该代理管理系统提供了完整的代理生命周期管理能力，并通过动态代理优先与静态池加权轮询实现高可用与负载均衡。内置的健康检查与自动禁用机制有效应对代理失效场景。配合统计接口与前端可视化，便于持续优化网络性能与成功率。

[本节为总结性内容，不直接分析具体文件]

## 附录：最佳实践与集成示例

### 代理类型与认证
- 支持的协议：HTTP、HTTPS、SOCKS5、SOCKS4
- 认证方式：将用户名/密码以 user:pass@host:port 形式嵌入 URL
- 示例（概念性）：
  - http://user:pass@1.2.3.4:8080
  - socks5://1.2.3.4:1080

章节来源
- [providers/proxy/api_extract.py:83-97](file://providers/proxy/api_extract.py#L83-L97)

### 连接池与负载均衡
- 区域路由：通过 region 参数限定代理范围
- 成功率加权：系统按 success/(success+fail) 排序，再轮询选取
- 建议：
  - 多区域部署时，按目标站点地域选择对应 region
  - 定期运行检测，保持成功率权重准确

章节来源
- [core/proxy_pool.py:14-45](file://core/proxy_pool.py#L14-L45)

### 故障转移与自动切换
- 连续失败阈值：当连续失败达到一定次数（例如 5 次）且从未成功过，自动禁用该代理
- 动态代理优先：若配置了动态代理，则优先使用，否则回退到静态池
- 建议：
  - 为关键业务开启动态代理，提升容错能力
  - 对静态池设置合理的检测周期与阈值

章节来源
- [core/proxy_pool.py:56-66](file://core/proxy_pool.py#L56-L66)
- [core/proxy_providers.py:77-102](file://core/proxy_providers.py#L77-L102)

### 供应商集成与批量导入
- 供应商模式：
  - api_extract：从 HTTP API 拉取代理列表（支持 JSON/文本）
  - rotating_gateway：固定网关，出口 IP 自动轮换
- 批量导入：
  - 支持一次传入多个代理 URL，自动去重与忽略空行
  - 可为整批指定 region

章节来源
- [core/proxy_providers.py:53-74](file://core/proxy_providers.py#L53-L74)
- [providers/proxy/api_extract.py:54-82](file://providers/proxy/api_extract.py#L54-L82)
- [providers/proxy/rotating_gateway.py:19-31](file://providers/proxy/rotating_gateway.py#L19-L31)
- [infrastructure/proxies_repository.py:38-51](file://infrastructure/proxies_repository.py#L38-L51)

### 监控与度量
- 代理成功率排行：/stats/by-proxy
- 前端面板：显示总量、启用数、成功/失败次数，支持一键检测
- 建议：
  - 基于成功率与活跃度调整代理策略
  - 对长期低成功率的代理进行下线或替换

章节来源
- [api/stats.py:110-132](file://api/stats.py#L110-L132)
- [frontend/src/pages/Proxies.tsx:41-76](file://frontend/src/pages/Proxies.tsx#L41-L76)