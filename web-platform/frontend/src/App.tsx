import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { Session } from '@supabase/supabase-js'
import { supabase } from './lib'
import Auth from './Auth'
import Dashboard from './Dashboard'
import Profile from './Profile'
import Settings from './Settings'
import Workspace from './Workspace'
import { Spinner } from './components'

function Shell() {
  return <div className="app-shell"><aside><Link to="/" className="brand">CareerFlow</Link><nav><NavLink to="/">岗位进度</NavLink><NavLink to="/profile">个人资料</NavLink><NavLink to="/settings">模型设置</NavLink></nav><div className="aside-foot"><button onClick={() => supabase.auth.signOut()}>退出登录</button><small>你的决定始终优先于Agent。</small></div></aside><main className="content"><Routes><Route path="/" element={<Dashboard />} /><Route path="/profile" element={<Profile />} /><Route path="/settings" element={<Settings />} /><Route path="/applications/:id" element={<Workspace />} /><Route path="*" element={<Navigate to="/" />} /></Routes></main></div>
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
  return session ? <Shell /> : <Auth />
}

