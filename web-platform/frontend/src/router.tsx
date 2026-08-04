import { AnchorHTMLAttributes, createContext, PropsWithChildren, useContext, useEffect, useMemo, useState } from 'react'

const RouterContext = createContext('/')

function currentPath() {
  const value = window.location.hash.replace(/^#/, '') || '/'
  return value.startsWith('/') ? value : `/${value}`
}

export function HashRouter({ children }: PropsWithChildren) {
  const [path, setPath] = useState(currentPath)
  useEffect(() => {
    const update = () => setPath(currentPath())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  return <RouterContext.Provider value={path}>{children}</RouterContext.Provider>
}

export function usePath() { return useContext(RouterContext) }

export function useNavigate() {
  return useMemo(() => (to: string) => {
    const safe = to.startsWith('/') && !to.startsWith('//') ? to : '/'
    window.location.hash = safe
  }, [])
}

export function useParams(): { id?: string } {
  const path = usePath()
  const match = /^\/applications\/([0-9a-f-]{36})$/.exec(path)
  return { id: match?.[1] }
}

export function Link({ to, children, ...props }: PropsWithChildren<AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }>) {
  const safe = to.startsWith('/') && !to.startsWith('//') ? to : '/'
  return <a {...props} href={`#${safe}`}>{children}</a>
}

export function NavLink({ to, children }: PropsWithChildren<{ to: string }>) {
  const path = usePath()
  const active = to === '/' ? path === '/' : path.startsWith(to)
  return <Link to={to} className={active ? 'active' : undefined}>{children}</Link>
}

export function Redirect({ to }: { to: string }) {
  const navigate = useNavigate()
  useEffect(() => navigate(to), [navigate, to])
  return null
}
