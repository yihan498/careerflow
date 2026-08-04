# CareerFlow 网站安全与可靠性审计（2026-08-04）

## 结论

> 修复状态（2026-08-04）：Critical 与 High 项均已完成代码修复并加入回归测试；Medium 项已完成安全头、持久任务租约、内部 Schema/配额、多邮箱、隐私自助、依赖和清理机制。生产环境仍需应用 `002_deletion_jobs.sql`、配置新增 Worker 变量、轮换旧共享密钥并重新部署后，才能视为线上关闭。CI 模板已放在 `deploy/ci-web-platform.yml`，为遵守子项目隔离边界尚未写入仓库根工作流。

当前版本可以继续用于受控测试，但**不建议在修复 SEC-001 前开放公众注册或宣传为可安全处理真实简历的正式服务**。

本次确认了：

- 1 个 Critical；
- 5 个 High；
- 8 个 Medium；
- 4 个 Low / 优化项。

最重要的问题不是未登录用户直接读取他人数据。抽查的岗位、文件、导出和复盘接口均能在未登录时返回 `401`，跨域配置也没有向陌生来源放行。主要风险集中在文档 Worker 的服务间鉴权、服务器主动请求边界、事实核验真实性，以及大文件交付和删除流程的可靠性。

## 审计范围与方法

- 静态检查：`web-platform/api`、`document-worker`、`frontend`、数据库迁移、部署配置与 CI。
- 线上只读检查：主页/API 安全响应头、CORS、OpenAPI 暴露、未登录 GET 接口。
- 自动检查：13 个 Python 测试、2 个前端测试、前端生产构建、隔离脚本。
- 依赖检查：`npm audit --omit=dev` 与 Python 依赖审计。
- 未创建账户、未上传文件、未调用模型、未触发文档任务，也未尝试利用已发现漏洞。

## 必须先修复

### SEC-001 — Critical — 文档 Worker 可泄露共享密钥并形成 SSRF

**证据**

- `document-worker/document_worker/main.py:19-25`：公网任务请求可由调用者指定 `source_url` 和 `callback_base_url`。
- `document-worker/document_worker/main.py:34-37`：Worker 把长期共享密钥放进 `X-Worker-Secret`。
- `document-worker/document_worker/main.py:99-117`：`POST /v1/jobs` 没有入站鉴权，随后向调用者指定的回调地址发送密钥，并下载调用者指定的 URL。
- `api/document_jobs.py:235-246`：主 API 调用 Worker 时没有附加 Worker 入站鉴权凭证。

**风险**

任何人都可以直接调用公开 Worker，把回调地址指向自己的服务器，从回调请求中取得全局 Worker 密钥；同时可诱导 Worker 请求任意 HTTP(S) 地址。共享密钥泄漏后，攻击者还可能伪造内部任务完成/失败回调。一次性任务令牌并不能阻止该问题，因为 Worker 在出站请求前没有本地验证令牌。

**修复要求**

1. `/v1/jobs` 必须验证 API→Worker 专用凭证。
2. 删除请求中的 `callback_base_url`；回调源必须来自 Worker 环境变量中的固定 API Origin。
3. Worker 在任何出站请求前本地验证任务签名、任务 ID、操作、文件哈希与过期时间。
4. `source_url` 仅允许固定 R2 私有桶签名 URL；阻止 localhost、私网、链路本地、IP 字面量、重定向跨域和 DNS rebinding。
5. 回调使用每任务凭证，不再仅依赖全局共享密钥。
6. 修复上线后轮换 `DOCUMENT_WORKER_SHARED_SECRET`。
7. 增加恶意 callback/source、缺少鉴权、重复令牌和 DNS 变化测试。

### SEC-002 — High — 模型 Base URL 允许服务器端任意请求

**证据**

- `api/schemas.py:10-16`：`base_url` 是无约束字符串。
- `api/providers.py:99-133`：服务端把该地址作为模型 endpoint，并携带用户 API Key 发出请求。
- `frontend/src/Settings.tsx:27-33`：页面允许自由填写 Base URL。

**风险**

已登录用户可让服务端访问 localhost、私网或云元数据地址；填写错误或被诱导填写恶意地址时，用户 API Key 也会被发送到该主机。

**修复要求**

首版七家固定服务商只允许服务端维护的精确 HTTPS Origin 和路径白名单。若未来支持自定义网关，应作为独立高级功能，阻止 IP 字面量、私网/链路本地地址、跨域重定向，并在连接前后重新校验 DNS 解析结果。

### AI-001 — High — “用户提供网页链接”并未抓取正文，却可被标记为 Verified

**证据**

- `frontend/src/Workspace.tsx:63`：页面称非原生搜索模型可使用用户提供的网页链接。
- `api/workflows.py:489-515,615-628`：后端只把 URL 字符串放进提示词，没有抓取或提取网页正文。
- `shared/careerflow_compat.py:59-75`：校验只要求九段标题、任意 URL 和至少一个证据标签。

**风险**

无法访问网页的模型可以编造事实，只要复述一个 URL 并写 `[Verified]` 就能通过校验。这违背了“无可靠来源时不能伪装成已完成调研”的核心承诺。

**修复要求**

增加受控网页获取与正文提取服务（同时做好 SSRF 防护），保存来源 URL、抓取时间、正文快照与哈希；每个 Verified 结论必须绑定 Evidence ID，并由程序验证 Evidence ID 确实对应已获取内容。无法取证时只能输出 `Unknown` 或调研框架。

### FLOW-001 — High — 原格式修改计划是可选项，审批可绕过原格式编辑

**证据**

- `frontend/src/Workspace.tsx:59-60`：修改计划在界面上是可选步骤。
- `api/workflows.py:332-365`：审批只要求草稿；没有计划时仍可走通通用构建。

**风险**

即使用户上传了 PDF/DOCX，也可以在没有查看区域修改计划的情况下审批，最终得到重新生成的通用 PDF，而不是保留原格式的文件。这会让产品承诺和实际结果不一致。

**修复要求**

只要岗位绑定了源简历模板，审批包就必须包含已校验的修改计划；通用构建只能作为用户明确选择的“无法保留原格式”降级模式。页面必须在审批前同时展示原文、新文、Evidence、区域/段落及宽度告警。

### REL-001 — High — EML 通过 JSON 返回，正常简历也可能超过 Vercel 4.5 MB 限制

**证据**

- `api/workflows.py:425-479`：后端把附件读入内存，再把完整 EML 放进 JSON。
- `frontend/src/Workspace.tsx:62`：前端把完整 EML 编码成 `data:` URL 下载。
- 当前上传上限为 10 MB，而 Vercel Function 请求/响应体上限为 4.5 MB。

**风险**

附件经过 Base64 后体积还会增大。只要简历稍大，邮件准备接口就可能返回 413 或在浏览器端耗费大量内存；这不是极端攻击场景，而是正常用户路径。

**修复要求**

服务端生成 `.eml` 不可变产物并上传 R2，API 只返回元数据和短时下载 URL。不要把附件或完整 EML 放进 JSON，也不要使用 `data:` URL。

参考：[Vercel Functions 4.5 MB 请求/响应限制](https://vercel.com/docs/functions/limitations)。

### DATA-001 — High — 删除账户/岗位不是原子操作，且 R2 只删除前 1000 个对象

**证据**

- `api/main.py:453-523`：先删 R2，再删数据库，最后删 Supabase Auth；任一步失败都会产生部分完成状态。
- `api/storage.py:49-53`：`delete_prefix` 只处理一次最多 1000 个对象，没有 continuation token 分页。

**风险**

可能出现文件已删但账户仍可登录、数据库已删但 Auth 删除失败，或大账户仍残留 R2 对象。当前实现无法满足“一键销毁后数据库、文件和 Key 全部消失”的验收要求。

**修复要求**

跨 Supabase/Postgres/R2 无法做真正单事务，应实现可恢复的删除 Saga：先冻结账户并建立 deletion job，分页列举/删除对象，逐项记录结果与重试，最后删除 Auth；向用户提供完成回执。岗位删除同样使用该机制。

## 上线前应修复

### SEC-003 — Medium — 公共 SPA 缺少安全响应头，登录令牌默认持久化在 localStorage

**证据**

- 线上主页没有 CSP、`X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy`；API 响应有这些头。
- `vercel.json:3-16` 只定义 build/rewrites，没有静态站点 headers。
- `frontend/src/lib.ts:1-5` 使用 Supabase 客户端默认 Auth 配置。

**风险**

Supabase 默认 `persistSession=true` 并把会话存入 localStorage。当前没有 CSP 防线时，一旦未来出现 XSS，持久化 access/refresh token 更容易被读取；同时页面可被 iframe 嵌入。

**修复要求**

为 Vercel 静态路由添加严格 CSP（精确允许 Supabase 与 Turnstile）、`frame-ancestors 'none'`、nosniff、Referrer-Policy 和 Permissions-Policy；评估自定义 sessionStorage 或 BFF/HttpOnly Cookie 架构，并缩短会话窗口。

参考：[Supabase JS 默认会持久化会话到 localStorage](https://supabase.com/docs/reference/javascript/auth)。

### SEC-004 — Medium — 内存限流不适用于 Serverless，也未落实单用户并发上限

**证据**

- `api/main.py:111-128`：限流计数器只存在当前 Python 进程内，并使用 `request.client.host`。
- 数据库中没有“每用户同时一个 Agent/文档任务”的唯一约束或持久锁。

**风险**

Vercel 多实例和冷启动会重置/分散计数；代理 IP 还可能导致误伤或绕过。用户可并发创建多个昂贵模型或文档任务，引发费用、状态竞态和资源耗尽。

**修复要求**

在边缘/WAF 与数据库两层限流；昂贵任务以 `user_id` 建立持久并发租约和超时回收。只有在代理信任配置正确时才使用真实客户端 IP。

### SEC-005 — Medium — 内部 Worker 回调和输出缺少严格 Schema/配额

**证据**

- `api/main.py:526-578`：内部 consume/complete/fail 接口使用裸 `dict`。
- `api/document_jobs.py:177-201`：可遍历任意数量文件并把输出全部读入内存。
- Worker 的单文件资源上限高于产品对源文件的 10 MB 限制。

**风险**

Worker 被攻破或密钥泄漏后，可提交超大/超多输出，导致内存、存储和响应耗尽。

**修复要求**

为内部回调建立严格 Pydantic Schema；限制文件数量、单文件/总大小、文件名、Content-Type 和允许的 artifact 类型；采用流式哈希与上传。

### REL-002 — Medium — 构建中断可能留下无法追踪的 R2 孤儿文件

**证据**

- `api/workflows.py:387-422`：先上传多个对象，最后才提交数据库；上传中途失败没有按已上传 key 清理。
- 维护任务只能发现数据库中已有记录的失败版本，无法发现从未入库的对象。

**风险**

反复失败会永久消耗免费存储额度，最终影响所有用户上传与预览。

**修复要求**

先创建 pending artifact manifest，再逐项上传；失败时可按 manifest 清理。对象 key 加入 job/version 标识，并定期对账数据库与 R2。

### UI-001 — Medium — 多邮箱邮件准备流程在前端无法完成

**证据**

- `api/workflows.py:425-479`：多邮箱时返回 `requires_selection` 和候选地址。
- `frontend/src/Workspace.tsx:62`：前端始终按最终 `Delivery` 处理，没有收件人选择分支。

**风险**

包含多个邮箱的 JD 会显示异常或生成失败，用户无法在网页内完成预期步骤。

**修复要求**

增加明确的收件人选择与二次确认；后端将“候选响应”和“最终交付响应”定义为可判别联合类型并完整测试。

### UI-002 — Medium — 隐私自助、总复盘和已生成面试稿缺少完整页面

**证据**

- `api/main.py:402-408,453-523` 已有总复盘、导出、删岗位、删账户 API。
- 前端没有相应入口；面试稿主要保存在组件瞬时状态中，刷新后不便继续查看。

**风险**

用户无法通过页面完成数据导出/销毁和经验汇总，产品所称“完整链路”仍依赖调用 API。

**修复要求**

增加账户与隐私中心、岗位删除确认、总复盘页、artifact 历史页；所有删除操作使用强确认但不隐藏。

### DEP-001 — Medium — 已安装前端和 Python 依赖存在已知公告

**证据**

- `react-router-dom@6.30.4` / `react-router@6.30.4`：`npm audit` 报告 2 个 moderate open redirect/XSS 相关公告。
- `cryptography` 约束为 `<46`，当前环境为 45.0.7，无法升级到多个 2026 公告的修复版本。

**边界**

当前路由主要使用常量和 UUID，React Router 公告的实际利用面较小；CareerFlow 对 cryptography 主要使用 AES-GCM，多个证书/椭圆曲线路径公告不直接适用。因此不将其评为 High，但依赖约束应尽快解除并回归测试。

**修复要求**

升级到受支持版本，增加 lockfile 审核、Dependabot/Renovate 和 CI dependency audit；升级 React Router 主版本时重点回归导航、鉴权与 HashRouter。

### CI-001 — Medium — CI 未覆盖 web-platform

**证据**

- `.github/workflows/ci.yml` 仅安装和测试根项目，没有运行 Web Python 测试、前端测试/构建、Worker 测试、隔离脚本或依赖审计。

**风险**

当前本地测试可通过，但部署分支缺少自动门禁，后续修改可能在没有任何 Web 测试的情况下发布。

**修复要求**

增加 Python 3.12 Web 测试、前端 `npm ci/test/build`、Worker 测试、隔离检查、迁移检查和依赖审计；部署前增加只读 smoke test。

## 较低风险与工程优化

### SEC-006 — Low — 生产环境公开 OpenAPI

- `/api/openapi.json`、`/api/docs` 和 Worker `/openapi.json` 可公开访问。
- 这不是独立安全边界，但会直接暴露内部回调字段和 Worker 危险参数。
- 生产环境应关闭或仅向管理员开放；尤其要在 SEC-001 修复前关闭 Worker OpenAPI。

### SEC-007 — Low — JWT 校验策略可更严格

- `api/auth.py:51-55` 从令牌 header 取得算法并作为允许算法，且未显式验证 issuer。
- 应使用固定算法白名单、固定 issuer/audience；遇到未知 `kid` 时主动刷新一次 JWKS，避免密钥轮换后最多一小时误拒绝。

### SUPPLY-001 — Low — Worker 依赖移动 Git 分支，部署不可复现

- `document-worker/pyproject.toml:10` 从 GitHub 的 `codex/web-platform` 分支安装 `careerflow-kit`。
- `docker-compose.yml` 使用 MinIO `latest`；Dockerfile 使用 `npm install` 而不是 `npm ci`。
- 应固定 commit/tag 与镜像 digest，并使用 lockfile 构建。

### PERF-001 — Low — 首屏 JS 可拆分，错误处理和公共信息仍可补齐

- 生产构建 JS 为 466.13 kB（gzip 135.33 kB），公共主页一次加载完整登录后工作区代码。
- `frontend/src/lib.ts:22` 对所有响应直接 `response.json()`，HTML 502/413 会覆盖真实错误。
- 可使用 route lazy loading、Error Boundary、AbortController、非 JSON 错误兜底；补充密码重置、隐私/条款入口、OG/canonical 和无障碍自动测试。

## 已确认做得正确的部分

- 抽查的受保护 GET 接口未登录均返回 `401`。
- 线上 CORS 对允许来源精确返回，对陌生来源不返回 ACAO。
- 数据访问大部分先按 `user_id` 和资源 ID 双重限定。
- API Key 使用 AES-256-GCM、随机 nonce、版本化密钥和关联数据；完整 Key 不回显。
- 上传实现了类型、magic bytes、大小、加密 PDF、DOCX ZIP 结构/解压体积检查。
- 文档任务有临时目录、超时和部分 POSIX 资源限制。
- RLS 已启用，并撤销 anon/authenticated 对业务表的直接权限。
- 未发现 `dangerouslySetInnerHTML`、`eval` 或明显 DOM XSS sink。
- 当前本地验证：Python `13 passed`；前端 `2 passed`；前端生产构建成功；隔离检查通过。

## 建议修复顺序

1. SEC-001：关闭 Worker 公开信任漏洞，轮换共享密钥。
2. SEC-002：锁死模型服务商 endpoint。
3. REL-001、DATA-001：改造 EML 下载和删除 Saga。
4. AI-001、FLOW-001：让证据链和原格式审批真正不可绕过。
5. SEC-003/004/005：响应头、持久限流、任务并发和输出配额。
6. UI-001/002：补齐多邮箱、隐私中心、总复盘与 artifact 页面。
7. DEP-001、CI-001、SUPPLY-001：升级依赖并建立发布门禁。
8. 最后完成公开测试账户的全链路 E2E，再开放注册。

## 验收门槛

公众开放前至少满足：

- Critical/High 全部关闭，并有回归测试；
- 恶意 callback/source/base URL 均被拒绝；
- 10 MB 文件不再经过 Vercel Function JSON 响应；
- 删除任务可分页、可重试、可出具完成记录；
- 非搜索模型不能在未获取正文时产生 Verified 结论；
- 上传了源模板的岗位不能跳过修改计划审批；
- Web CI、依赖审计和部署 smoke test 全部为绿色。
