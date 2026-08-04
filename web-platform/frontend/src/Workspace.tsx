import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, idempotencyKey, sessionId } from './lib'
import { Application, DraftBundle } from './types'
import { Button, Field, Notice, Spinner, StageBadge } from './components'

type Tab = 'overview' | 'draft' | 'delivery' | 'interview' | 'review'
type Artifact = { id: string; kind: string; size_bytes: number }
type Delivery = { recipient: string; subject: string; attachment_name: string; body: string; eml: string }

export default function Workspace() {
  const { id = '' } = useParams()
  const [application, setApplication] = useState<Application>()
  const [tab, setTab] = useState<Tab>('overview')
  const [provider, setProvider] = useState('deepseek')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [draft, setDraft] = useState<DraftBundle>()
  const [delivery, setDelivery] = useState<Delivery>()
  const [sources, setSources] = useState('')
  const [brief, setBrief] = useState('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [review, setReview] = useState({ outcome: 'pending', actual_questions: [''], answers: [''], feelings: '', strengths: '', improvements: '' })
  const load = async () => {
    const value = await api<Application>(`/api/v1/applications/${id}`)
    setApplication(value); setDraft(value.draft_bundle)
  }
  useEffect(() => { void load().catch(e => setError(e.message)) }, [id])
  useEffect(() => {
    if (application && ['built', 'submitted', 'interviewing', 'closed'].includes(application.stage)) {
      void api<Artifact[]>(`/api/v1/applications/${id}/artifacts`).then(setArtifacts)
    }
  }, [application?.stage, id])
  async function action<T>(work: () => Promise<T>, success: string) {
    setBusy(true); setError(''); setMessage('')
    try { const result = await work(); setMessage(success); await load(); return result }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  if (!application) return <section className="panel">{error ? <Notice tone="error">{error}</Notice> : <Spinner />}</section>
  const app = application
  const canDraft = ['created', 'drafted'].includes(app.stage)
  const canApprove = app.stage === 'drafted'
  const canBuild = app.stage === 'approved'
  const canDeliver = ['built', 'submitted', 'interviewing', 'closed'].includes(app.stage)
  const tabLabels: Record<Tab, string> = { overview: '岗位', draft: '简历与求职信', delivery: '投递', interview: '面试', review: '复盘' }
  const run = (path: string, body?: unknown) => api(`/api/v1/applications/${id}/${path}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined })
  async function downloadArtifact(artifactId: string) {
    const data = await api<{ url: string }>(`/api/v1/artifacts/${artifactId}/download`); location.href = data.url
  }
  return <section className="workspace">
    <header className="workspace-head"><div><small>{app.company}</small><h1>{app.role}</h1></div><StageBadge stage={app.stage} /></header>
    <nav className="tabs">{(Object.keys(tabLabels) as Tab[]).map(name => <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>{tabLabels[name]}</button>)}</nav>
    {error && <Notice tone="error">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
    {tab === 'overview' && <div className="panel"><h2>完整 JD</h2><pre className="jd">{app.jd}</pre><div className="action-bar"><Provider value={provider} onChange={setProvider} /><Button disabled={!canDraft || busy} onClick={() => { void action(() => run('draft', { provider, session_id: sessionId, idempotency_key: idempotencyKey('draft') }), '草稿已生成，请逐项检查。').then(() => setTab('draft')) }}>{busy ? <Spinner /> : '生成申请材料'}</Button></div></div>}
    {tab === 'draft' && <div className="panel">
      {draft ? <div className="draft-grid"><Field label="简历草稿"><textarea value={draft.resume_markdown} onChange={e => setDraft({ ...draft, resume_markdown: e.target.value })} /></Field><Field label="Cover Letter"><textarea value={draft.cover_letter_markdown} onChange={e => setDraft({ ...draft, cover_letter_markdown: e.target.value })} /></Field><Field label="Evidence Map"><textarea value={draft.evidence_map_markdown} onChange={e => setDraft({ ...draft, evidence_map_markdown: e.target.value })} /></Field></div> : <Notice>尚未生成草稿。</Notice>}
      {app.document_plan && <details className="plan-review"><summary>查看原格式修改计划（审批包的一部分）</summary><pre>{JSON.stringify(app.document_plan, null, 2)}</pre></details>}
      <div className="actions">{draft && <Button variant="secondary" onClick={() => { void action(() => api(`/api/v1/applications/${id}/draft`, { method: 'PUT', body: JSON.stringify({ bundle: draft, document_plan: app.document_plan || null }) }), '修改已保存；旧审批已失效。') }}>保存修改</Button>}{draft && !app.document_plan && <Button variant="secondary" onClick={() => { void action(() => run('document-plan', { provider, session_id: sessionId, idempotency_key: idempotencyKey('document-plan'), template_id: 'default' }), '原格式修改计划已生成。') }}>生成原格式修改计划</Button>}<Button disabled={!canApprove || busy} onClick={() => { void action(() => run('approve'), '审批包已锁定。') }}>确认全部内容</Button><Button disabled={!canBuild || busy} onClick={() => { const endpoint = app.document_plan ? 'document-build' : 'build'; void action(() => run(endpoint), '构建完成。') }}>构建最终文件</Button></div>
    </div>}
    {tab === 'delivery' && <div className="panel"><h2>投递准备</h2><p>CareerFlow 只准备邮件，不连接或代发邮箱。</p><div className="artifact-list">{artifacts.map(item => <button key={item.id} onClick={() => { void downloadArtifact(item.id) }}>{item.kind}<small>{Math.ceil(item.size_bytes / 1024)} KB</small></button>)}</div><Button disabled={!canDeliver} onClick={() => { void action(() => api<Delivery>(`/api/v1/applications/${id}/delivery`), '邮件材料已生成。').then(value => value && setDelivery(value)) }}>生成邮件预览</Button>{delivery && <div className="email-preview"><b>收件人：</b>{delivery.recipient}<br/><b>主题：</b>{delivery.subject}<br/><b>附件：</b>{delivery.attachment_name}<pre>{delivery.body}</pre><a download={`${delivery.subject}.eml`} href={`data:message/rfc822;charset=utf-8,${encodeURIComponent(delivery.eml)}`}>下载 .eml</a></div>}<Button disabled={app.stage !== 'built'} onClick={() => { void action(() => run('submitted'), '已记录为用户自行投递。') }}>我已经自行发送</Button></div>}
    {tab === 'interview' && <div className="panel"><h2>面试准备</h2><Provider value={provider} onChange={setProvider} /><Field label="资料链接" hint="其他模型必须提供 URL；OpenAI/通义可在通过能力测试后原生搜索。"><textarea value={sources} onChange={e => setSources(e.target.value)} /></Field><Button disabled={!canDeliver || busy} onClick={() => { const urls = sources.split(/\s+/).filter(Boolean); void action(() => run('interview', { provider, session_id: sessionId, idempotency_key: idempotencyKey('interview'), source_urls: urls, use_native_search: ['openai', 'qwen'].includes(provider) && urls.length === 0 }), '面试材料已生成。').then(value => { if (value && typeof value === 'object' && 'brief' in value) setBrief(String((value as { brief: unknown }).brief)) }) }}>开始调研和问题预测</Button>{brief && <pre className="brief">{brief}</pre>}</div>}
    {tab === 'review' && <div className="panel stack"><h2>面试复盘</h2><Field label="结果"><select value={review.outcome} onChange={e => setReview({ ...review, outcome: e.target.value })}><option value="pending">等待结果</option><option value="rejected">未通过</option><option value="withdrew">主动退出</option><option value="offer">获得 Offer</option></select></Field><Field label="实际问题"><textarea value={review.actual_questions.join('\n')} onChange={e => setReview({ ...review, actual_questions: e.target.value.split('\n') })} /></Field><Field label="自己的回答"><textarea value={review.answers.join('\n')} onChange={e => setReview({ ...review, answers: e.target.value.split('\n') })} /></Field><Field label="感受"><textarea value={review.feelings} onChange={e => setReview({ ...review, feelings: e.target.value })} /></Field><Field label="做得好的部分"><textarea value={review.strengths} onChange={e => setReview({ ...review, strengths: e.target.value })} /></Field><Field label="需要改进"><textarea value={review.improvements} onChange={e => setReview({ ...review, improvements: e.target.value })} /></Field><Button disabled={!canDeliver} onClick={() => { void action(() => run('review', { feedback: review }), '复盘已原子同步到个人汇总。') }}>保存并同步复盘</Button></div>}
  </section>
}

function Provider({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <Field label="本次使用模型"><select value={value} onChange={e => onChange(e.target.value)}><option value="deepseek">DeepSeek</option><option value="qwen">通义千问</option><option value="openai">OpenAI</option><option value="zhipu">智谱 GLM</option><option value="kimi">Kimi</option><option value="minimax">MiniMax</option><option value="doubao">豆包</option></select></Field>
}
