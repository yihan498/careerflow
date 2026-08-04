# Security Model

## 信任边界

- web-api：身份、状态机、模型调用、审批与签名 URL；禁止解析原始 Office/PDF。
- document-worker：一次只处理一个指定对象；不持有数据库、模型 Key、主密钥或存储桶列举权限。
- 浏览器：只持有 Supabase 会话与随机凭证会话 ID，不持有服务端主密钥。

## 强制控制

- 资源查询同时匹配资源 ID 与登录用户 ID，数据库表启用 RLS，并撤销客户端直接表权限。
- 文档令牌绑定 job、操作、源文件 SHA-256 和过期时间，数据库原子消费一次；令牌不落库明文。
- Worker 校验文件魔数、哈希、ZIP 条目数/总体积/路径穿越，使用独立临时目录、清空敏感环境变量，并限制 CPU、内存、文件数与执行时间。
- R2 私有，浏览器和 worker 仅获得短时对象级签名 URL；下载强制 `Content-Disposition: attachment`。
- 凭证使用独立随机 nonce、AAD 绑定用户/厂商及版本化 AES-256-GCM 主密钥。
- CSP、HSTS（生产）、严格 CORS、nosniff、DENY frame 与任务限速默认启用。

## 已知边界

- 免费 Render 不提供生产 SLA，冷启动和资源回收可能令任务失败；失败状态必须保留在当前阶段。
- 首版不 OCR 扫描 PDF。
- DOCX 在免费环境无法稳定渲染时只标记为“需 Word 目视确认”，不声称完全验证。
- 只有通过契约测试的 OpenAI/通义配置开放原生搜索；其他厂商必须由用户提供来源链接。

发现安全问题时请使用 GitHub Security Advisory 私下报告，不要在公开 Issue 中粘贴简历、API Key 或签名 URL。
