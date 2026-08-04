import { useEffect, useState } from 'react'
import { Link, NavLink, Redirect, usePath } from './router'
import { Session } from '@supabase/supabase-js'
import { supabase } from './lib'
import Auth from './Auth'
import Dashboard from './Dashboard'
import Landing from './Landing'
import Profile from './Profile'
import Settings from './Settings'
import Workspace from './Workspace'
import Account from './Account'
import Privacy from './Privacy'
import { Spinner } from './components'

function Shell() {
  const path = usePath()
  const page = path === '/' ? <Dashboard /> : path === '/profile' ? <Profile /> : path === '/settings' ? <Settings /> : path === '/account' ? <Account /> : /^\/applications\/[0-9a-f-]{36}$/.test(path) ? <Workspace /> : <Redirect to="/" />
  return <div className="app-shell"><aside><Link to="/" className="brand">CareerFlow</Link><nav><NavLink to="/">岗位进度</NavLink><NavLink to="/profile">个人资料</NavLink><NavLink to="/settings">模型设置</NavLink><NavLink to="/account">复盘与隐私</NavLink></nav><div className="aside-foot"><button onClick={() => supabase.auth.signOut()}>退出登录</button><small>你的决定始终优先于Agent。</small></div></aside><main className="content">{page}</main></div>
}

function PublicShell() {
  const path = usePath()
  return path === '/' ? <Landing /> : path === '/auth' ? <Auth /> : path === '/privacy' ? <Privacy /> : <Redirect to="/" />
}

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const development = import.meta.env.VITE_DEV_AUTH_BYPASS === 'true'
  useEffect(() => {
    if (development) { setSession({} as Session); return }
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [development])
  if (session === undefined) return <div className="center"><Spinner text="正在检查会话…" /></div>
  return session ? <Shell /> : <PublicShell />
}
