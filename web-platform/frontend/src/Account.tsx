import { useEffect, useState } from 'react'
import { useNavigate } from './router'
import { api, supabase } from './lib'
import { Button, Notice } from './components'

export default function Account() {
  const navigate = useNavigate()
  const [reviews, setReviews] = useState<Record<string, unknown[]>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { api<Record<string, unknown[]>>('/api/v1/reviews').then(setReviews).catch(e => setError(e.message)) }, [])

  async function exportData() {
    setBusy(true); setError('')
    try {
      const data = await api<unknown>('/api/v1/account/export')
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a'); link.href = url; link.download = 'careerflow-export.json'; link.click()
      URL.revokeObjectURL(url)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function deleteAccount() {
    if (!window.confirm('这会永久删除账户、所有岗位、文件和API Key。确定继续吗？')) return
    setBusy(true); setError('')
    try {
      await api('/api/v1/account', { method: 'DELETE' })
      await supabase.auth.signOut()
      navigate('/')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return <section className="stack">
    <div className="panel"><h1>复盘汇总</h1><p className="muted">原始反馈按问题类型汇总，不改写你的记录。</p>{Object.entries(reviews).map(([category, entries]) => <details key={category} className="plan-review"><summary>{category}（{entries.length}）</summary><pre>{JSON.stringify(entries, null, 2)}</pre></details>)}{!Object.keys(reviews).length && <p className="muted">尚无复盘记录。</p>}</div>
    <div className="panel"><h1>数据与隐私</h1><p>简历和JD只会在你确认后发送给所选模型服务商；模型厂商的数据保留政策仍由相应厂商决定。</p><p className="muted">你可以随时导出全部结构化数据和短时文件下载地址，或发起可重试的一键销毁。</p>{error && <Notice tone="error">{error}</Notice>}<div className="actions"><Button variant="secondary" disabled={busy} onClick={() => void exportData()}>导出全部数据</Button><Button variant="danger" disabled={busy} onClick={() => void deleteAccount()}>永久删除账户</Button></div></div>
  </section>
}
