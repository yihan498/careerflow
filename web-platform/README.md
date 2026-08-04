# CareerFlow Web Platform

CareerFlow 的公网 BYOK（Bring Your Own Key）网页版。它把“确认简历事实 → 按 JD 生成材料 → 原格式修改 → 人工审批 → 构建文件 → 准备投递 → 面试调研 → 复盘沉淀”做成一条有状态、可追踪、可中断恢复的流程。

本目录是独立工程。它不会修改仓库已有 CLI、文档引擎、测试或用户案例；仅在隔离文档服务中复用公开版的文档处理能力。

## 设计边界

- Agent 只产生候选内容，不能批准、推进状态或发送邮件。
- 每个岗位拥有独立 ID、JD、材料、审批哈希、文件版本和复盘。
- `submitted` 只由用户在外部自行发送后确认；`interviewing` 只由用户主动启动。
- PDF/DOCX 原文件仅交给隔离的 document-worker；worker 不持有模型 Key、数据库管理凭证或 R2 列举权限。
- 所有构建物不可变。只有全套上传并校验哈希成功后，数据库才原子切换有效版本。
- CareerFlow 不接收邮箱密码、不登录邮箱、不发送邮件；只生成附件和 `.eml`。

状态机固定为：

```text
onboarding → created → drafted → approved → built → submitted → interviewing → closed
```

已审批包发生任何字符变化时，审批立即失效并回到 `drafted`。

## 目录

```text
web-platform/
├─ frontend/          React + Vite
├─ api/               FastAPI、状态机、模型适配、审批与数据权限
├─ document-worker/   隔离 PDF/DOCX 检查和写回
├─ shared/            共享 Schema、状态与错误契约
├─ migrations/        PostgreSQL/Supabase 结构和 RLS
├─ deploy/            Render 双服务镜像和 Blueprint
├─ tests/             新平台测试
└─ scripts/           隔离检查
```

## 用户如何使用

1. 注册并验证邮箱。
2. 选择 OpenAI、DeepSeek、通义千问、智谱 GLM、Kimi、MiniMax 或豆包，填入自己创建的低额度专用 API Key。默认 Key 8 小时后失效，只有主动选择才持久保存。
3. 上传 PDF/DOCX 简历。系统先检查文件、抽取文字和区域；扫描 PDF 没有文字层时会停止，不会伪装成功。
4. 明确确认“把简历文字发送给所选模型”，逐项核对事实并建立 Evidence Library。
5. 新建岗位并粘贴完整 JD。每个岗位完全隔离。
6. 生成并审阅简历草稿、Cover Letter、Evidence Map 和原格式修改计划。
7. 人工批准整个内容包后构建文件。DOCX 若无法稳定服务端渲染，会提示下载后在 Word 中目视确认。
8. 系统从 JD 提取邮箱并生成附件名、主题、正文和 `.eml`。用户自行发送后手动标记已投递。
9. 用户收到面试或决定提前准备时，主动启动面试调研；实时事实必须带 URL，并区分 Verified / Inference / Unknown。
10. 面试后填写原始反馈。Agent 只分类和提出训练动作，原始反馈保持不变，同时原子更新岗位复盘与总复盘。

## 本地启动

要求 Docker Desktop 和 Docker Compose。

```powershell
Copy-Item .env.example .env
docker compose up --build
```

本地入口为 `http://localhost:8000`。默认 compose 使用本地 PostgreSQL、MinIO、开发身份绕过和两个独立服务。仅本地开发可使用 `DEV_AUTH_BYPASS=true`；生产环境启动时会拒绝该配置。

不使用 Docker 时：

```powershell
Set-Location ..
python -m pip install ".[pdf]"
Set-Location web-platform
python -m pip install -e ".[dev,documents]"
Set-Location frontend
npm install
npm run build
Set-Location ..
uvicorn api.main:app --reload
```

## 配置

复制 `.env.example` 后配置：

- Supabase：`DATABASE_URL`、`SUPABASE_URL`、`SUPABASE_JWKS_URL`、`SUPABASE_SERVICE_ROLE_KEY`
- R2：endpoint、access key、secret、bucket、region；桶必须私有
- 安全密钥：32 字节 base64 的 `CREDENTIAL_MASTER_KEY`，以及彼此不同的 document token、Worker callback secret 和 API→Worker request secret
- Worker：公网 URL 与固定 API callback URL；每次 R2 签名下载 URL 的完整哈希会绑定进一次性任务令牌
- Turnstile：站点和服务端密钥
- 前端构建：`VITE_SUPABASE_URL`、`VITE_SUPABASE_ANON_KEY`、`VITE_TURNSTILE_SITE_KEY`
- Supabase Auth：配置 Resend SMTP，不能依赖默认邮件服务面向公众发信

生产凭证不得提交到 Git。Key 完整值不会回显，也不应进入反向代理访问日志。

## 测试

```powershell
python -m pytest
Set-Location frontend
npm test -- --run
npm run build
npm audit --omit=dev --audit-level=high
Set-Location ..
powershell -ExecutionPolicy Bypass -File scripts/verify-isolation.ps1
```

`deploy/ci-web-platform.yml` 是完整 Web 检查模板。仓库维护者启用时应将它合并到仓库根 `.github/workflows/`；模板保留在 `web-platform/` 内，以遵守本子项目不改动原工程的隔离边界。

真实模型 API 测试必须显式启用，CI 默认只运行模拟契约测试，不读取真实 Key。原仓库测试仍应从仓库根目录按原 README 执行。

## 部署

`deploy/render.yaml` 创建 web-api 和 document-worker 两个 Render 免费服务。数据库用 Supabase，私有文件用 Cloudflare R2，验证邮件用 Resend，滥用防护用 Turnstile。

正式部署前仍需由项目所有者提供子域名并创建以上免费账户，然后逐项填入环境变量、先执行 `migrations/001_initial.sql`、限制 worker 只能访问明确对象、配置 DNS 和 Supabase redirect URL。`002_deletion_jobs.sql` 是纯增量幂等迁移，生产 API 启动时会使用 PostgreSQL advisory lock 自动应用。Worker 必须额外配置 `DOCUMENT_WORKER_REQUEST_SECRET`、`DOCUMENT_TOKEN_SECRET` 与 `DOCUMENT_CALLBACK_BASE_URL`，并在安全升级后轮换原 `DOCUMENT_WORKER_SHARED_SECRET`。`DOCUMENT_SOURCE_ORIGINS` 是可选的额外 Origin 白名单。无需购买付费服务。

Render 免费服务存在冷启动、休眠和资源限制，本项目明确定位为免费测试版，不承诺生产级 SLA。开放注册必须经过虚构资料全链路验收、少量受控用户测试、容量/错误率/安全检查三个发布门槛。

## 数据与隐私

用户数据保留到主动删除。页面提供单岗位删除、Key 删除、完整导出和账户一键销毁。选择模型后，确认过的简历文字与 JD 会发送给对应厂商；CareerFlow 无法替代厂商的数据保留政策。详见 [PRIVACY.md](PRIVACY.md) 与 [SECURITY.md](SECURITY.md)。
