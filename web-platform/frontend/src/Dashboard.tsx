import { FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from './lib'
import { Application } from './types'
import { Button, Field, Notice, StageBadge } from './components'

export default function Dashboard() {
  const [items, setItems] = useState<Application[]>([])
  const [showNew, setShowNew] = useState(false)
  const [company, setCompany] = useState('')
  const [role, setRole] = useState('')
  const [jd, setJd] = useState('')
  const [error, setError] = useState('')
  const load = () => api<Application[]>('/api/v1/applications').then(setItems).catch(e => setError(e.message))
  useEffect(() => { void load() }, [])
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    try {
      await api('/api/v1/applications', { method: 'POST', body: JSON.stringify({ company, role, jd }) })
      setCompany(''); setRole(''); setJd(''); setShowNew(false); await load()
    } catch (e) { setError((e as Error).message) }
  }
  return <section className="panel">
    <div className="heading-row"><div><h1>岗位进度</h1><p className="muted">每个岗位独立保存，不共享审批和产物。</p></div><Button onClick={() => setShowNew(true)}>新建岗位</Button></div>
    {error && <Notice tone="error">{error}</Notice>}
    {showNew && <form className="new-job" onSubmit={submit}>
      <Field label="公司"><input required value={company} onChange={e => setCompany(e.target.value)} /></Field>
      <Field label="岗位"><input required value={role} onChange={e => setRole(e.target.value)} /></Field>
      <Field label="完整 JD" hint={`${jd.length}/200000`}><textarea required minLength={80} value={jd} onChange={e => setJd(e.target.value)} /></Field>
      <div className="actions"><Button type="button" variant="secondary" onClick={() => setShowNew(false)}>取消</Button><Button>建立岗位</Button></div>
    </form>}
    <div className="application-grid">
      {items.map(item => <Link className="application-card" to={`/applications/${item.id}`} key={item.id}><div><small>{item.company}</small><h2>{item.role}</h2></div><StageBadge stage={item.stage} /><p>最近更新：{new Date(item.history.at(-1)?.at || '').toLocaleDateString()}</p></Link>)}
      {!items.length && <div className="empty">还没有岗位。确认个人事实后，从一个完整 JD 开始。</div>}
    </div>
  </section>
}
