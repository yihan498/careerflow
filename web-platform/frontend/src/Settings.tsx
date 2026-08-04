import { FormEvent, useEffect, useState } from 'react'
import { api, sessionId } from './lib'
import { Provider } from './types'
import { Button, Field, Notice, Spinner } from './components'

export default function Settings() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [provider, setProvider] = useState('deepseek')
  const selected = providers.find(item => item.id === provider)
  const [key, setKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [save, setSave] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { api<Provider[]>('/api/v1/providers').then(setProviders).catch(e => setError(e.message)) }, [])
  useEffect(() => { if (selected) { setBaseUrl(selected.default_base_url); setModel(selected.default_model) } }, [selected?.id])

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      await api('/api/v1/providers/session', { method: 'PUT', body: JSON.stringify({ provider, api_key: key, base_url: baseUrl, model, save, session_id: sessionId }) })
      setMessage(save ? '连接成功，Key已加密保存。' : '连接成功，Key将在8小时后失效。'); setKey('')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <section className="panel narrow"><h1>模型设置</h1><p className="muted">建议创建专用、低额度Key。完整Key不会再次显示。</p>
    <form onSubmit={submit} className="stack">
      <Field label="服务商"><select value={provider} onChange={e => setProvider(e.target.value)}>{providers.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}</select></Field>
      <Field label="API Key"><input type="password" required minLength={8} value={key} onChange={e => setKey(e.target.value)} autoComplete="off" /></Field>
      <Field label="官方API地址"><input readOnly value={baseUrl} aria-describedby="provider-endpoint-help" /></Field>
      <p id="provider-endpoint-help" className="muted">为防止密钥误发和服务器请求内网，当前只允许经过验证的官方地址。</p>
      <Field label={selected?.requires_endpoint_id ? 'Endpoint ID' : '模型ID'}><input required value={model} onChange={e => setModel(e.target.value)} /></Field>
      <label className="check"><input type="checkbox" checked={save} onChange={e => setSave(e.target.checked)} />加密保存，不必每次填写</label>
      {error && <Notice tone="error">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
      <Button disabled={busy}>{busy ? <Spinner text="测试连接…" /> : '测试并使用'}</Button>
    </form>
  </section>
}
