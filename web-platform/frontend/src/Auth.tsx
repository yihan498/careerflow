import { FormEvent, useState } from 'react'
import { Link } from './router'
import { Turnstile } from '@marsidev/react-turnstile'
import { supabase } from './lib'
import { Button, Field, Notice } from './components'

export default function Auth() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [captcha, setCaptcha] = useState<string>()
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    if (siteKey && !captcha) { setError('请先完成人机验证。'); return }
    const options = captcha ? { captchaToken: captcha } : undefined
    const result = mode === 'signin'
      ? await supabase.auth.signInWithPassword({ email, password, options })
      : await supabase.auth.signUp({ email, password, options })
    if (result.error) setError(result.error.message)
    else if (mode === 'signup') setMessage('验证邮件已发送。验证后即可登录。')
  }

  return <main className="auth-shell">
    <section className="auth-copy">
      <Link to="/" className="brand auth-brand">CareerFlow</Link>
      <h1>让每一次求职，都留下可以复用的经验。</h1>
      <p>从JD、简历和求职信，到面试调研与复盘。每个岗位独立记录，每一步都由你确认。</p>
      <ul><li>使用你自己的模型API Key</li><li>保留原有PDF或Word格式</li><li>不会替你自动发送邮件</li></ul>
    </section>
    <form className="auth-card" onSubmit={submit}>
      <Link to="/" className="auth-back">← 返回主页</Link>
      <h2>{mode === 'signin' ? '登录' : '创建账户'}</h2>
      <Field label="邮箱"><input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></Field>
      <Field label="密码" hint="至少8位，建议使用独立密码"><input type="password" minLength={8} required value={password} onChange={e => setPassword(e.target.value)} /></Field>
      {siteKey && <Turnstile siteKey={siteKey} onSuccess={setCaptcha} />}
      {error && <Notice tone="error">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
      <Button type="submit" disabled={Boolean(siteKey && !captcha)}>{mode === 'signin' ? '登录' : '注册并验证邮箱'}</Button>
      <button type="button" className="text-button" onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}>
        {mode === 'signin' ? '还没有账户？注册' : '已有账户？登录'}
      </button>
    </form>
  </main>
}
