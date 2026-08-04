import { Link } from './router'

export default function Privacy() {
  return <main className="landing"><section className="landing-section privacy-page"><Link to="/" className="brand">CareerFlow</Link><h1>隐私与数据边界</h1><p>CareerFlow 保存你主动上传的简历、岗位JD、生成产物、审批与复盘记录，直到你主动删除。</p><h2>模型服务商</h2><p>只有在你确认并启动任务后，相应的简历文本、JD或调研材料才会发送给你选择的模型服务商。CareerFlow 无法替代各模型厂商的数据保留政策。</p><h2>API Key</h2><p>临时Key默认8小时失效；主动保存的Key使用服务端加密存储。完整Key不会回显，也不会发送给文档处理服务。</p><h2>导出与删除</h2><p>登录后可在“复盘与隐私”中导出数据、删除单个岗位或永久删除账户。删除任务可以安全重试，避免只删除一部分。</p><Link to="/auth" className="landing-primary">登录并管理数据</Link></section></main>
}
