import { useEffect, useState } from 'react'
import { api, idempotencyKey, sessionId } from './lib'
import { CandidateProfile } from './types'
import { Button, Field, Notice, Spinner } from './components'

const emptyProfile: CandidateProfile = { display_name: '', headline: '', education: [], experiences: [], skills: [], uncertainties: [] }

export default function Profile() {
  const [profile, setProfile] = useState<CandidateProfile>(emptyProfile)
  const [confirmed, setConfirmed] = useState(false)
  const [resumeText, setResumeText] = useState('')
  const [provider, setProvider] = useState('deepseek')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => { api<{ profile: CandidateProfile; confirmed: boolean } | null>('/api/v1/profile').then(data => { if (data) { setProfile(data.profile); setConfirmed(data.confirmed) } }).catch(() => undefined) }, [])

  async function upload(file?: File) {
    if (!file) return
    setBusy(true); setError('')
    const form = new FormData(); form.append('file', file)
    try {
      const data = await api<{ extracted_text: string }>('/api/v1/profile/resume', { method: 'POST', body: form })
      setResumeText(data.extracted_text); setMessage('文件检查通过。确认后才会把下方文字发送给模型。')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function extract() {
    setBusy(true); setError('')
    try {
      const data = await api<CandidateProfile>('/api/v1/profile/extract', { method: 'POST', body: JSON.stringify({ resume_text: resumeText, provider, session_id: sessionId, consent_to_provider: true, idempotency_key: idempotencyKey('profile') }) })
      setProfile(data); setConfirmed(false); setMessage('提取完成。请逐项检查，尤其是日期、数字和成果。')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function confirm() {
    setBusy(true); setError('')
    try { await api('/api/v1/profile/confirm', { method: 'POST', body: JSON.stringify({ profile }) }); setConfirmed(true); setMessage('事实资料已确认，可以新建岗位。') }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return <section className="panel"><div className="heading-row"><div><h1>个人资料</h1><p className="muted">Agent只能使用你确认过的事实。</p></div>{confirmed && <span className="verified">已确认</span>}</div>
    <div className="two-col">
      <div className="stack card-subtle"><h2>1. 读取原始简历</h2><input type="file" accept=".pdf,.docx" onChange={e => upload(e.target.files?.[0])} />
        <Field label="服务商"><select value={provider} onChange={e => setProvider(e.target.value)}><option value="deepseek">DeepSeek</option><option value="qwen">通义千问</option><option value="openai">OpenAI</option><option value="zhipu">智谱GLM</option><option value="kimi">Kimi</option><option value="minimax">MiniMax</option><option value="doubao">豆包</option></select></Field>
        {resumeText && <><textarea className="source-text" value={resumeText} onChange={e => setResumeText(e.target.value)} /><Button onClick={extract} disabled={busy}>确认发送并提取事实</Button></>}
      </div>
      <div className="stack"><h2>2. 检查并确认</h2>
        <Field label="姓名"><input value={profile.display_name} onChange={e => setProfile({ ...profile, display_name: e.target.value })} /></Field>
        <Field label="个人定位"><input value={profile.headline} onChange={e => setProfile({ ...profile, headline: e.target.value })} /></Field>
        <Field label="技能（逗号分隔）"><input value={profile.skills.join('，')} onChange={e => setProfile({ ...profile, skills: e.target.value.split(/[，,]/).map(x => x.trim()).filter(Boolean) })} /></Field>
        <h3>教育</h3>{profile.education.map((item, index) => <div className="inline-grid" key={index}><input aria-label="学校" value={item.school} onChange={e => { const education = [...profile.education]; education[index] = { ...item, school: e.target.value }; setProfile({ ...profile, education }) }} /><input aria-label="专业" value={item.program} onChange={e => { const education = [...profile.education]; education[index] = { ...item, program: e.target.value }; setProfile({ ...profile, education }) }} /><input aria-label="时间" value={item.period} onChange={e => { const education = [...profile.education]; education[index] = { ...item, period: e.target.value }; setProfile({ ...profile, education }) }} /></div>)}
        <h3>经历</h3>{profile.experiences.map((item, index) => <article className="experience" key={item.id}><strong>{item.organization} · {item.role}</strong><small>{item.period}</small>{item.bullets.map((bullet, bulletIndex) => <textarea key={bulletIndex} value={bullet} onChange={e => { const experiences = structuredClone(profile.experiences); experiences[index].bullets[bulletIndex] = e.target.value; setProfile({ ...profile, experiences }) }} />)}</article>)}
        {profile.uncertainties.length > 0 && <Notice tone="info">待核实：{profile.uncertainties.join('；')}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
        <Button onClick={confirm} disabled={busy || !profile.display_name || profile.experiences.length === 0}>{busy ? <Spinner /> : '确认全部事实'}</Button>
      </div>
    </div>
  </section>
}

