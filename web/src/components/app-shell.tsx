import { Link, useRouterState } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import { ArrowRight, Moon, ScanText, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { sessionOptions } from "@/lib/session"

function useSession() {
  return useQuery(sessionOptions)
}

function ThemeToggle() {
  const [dark, setDark] = useState(false)
  useEffect(() => { setDark(document.documentElement.dataset.theme === "dark") }, [])
  const toggle = () => {
    const next = !dark
    document.documentElement.dataset.theme = next ? "dark" : "light"
    localStorage.setItem("pagequay-theme", next ? "dark" : "light")
    setDark(next)
  }
  return <Button type="button" variant="outline" className="theme-toggle" onClick={toggle} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>{dark ? <Sun size={16} /> : <Moon size={16} />}<span>{dark ? "Light" : "Dark"}</span></Button>
}

function SignIn() {
  const queryClient = useQueryClient()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const login = useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      })
      const body = await response.json() as { error?: string }
      if (!response.ok) throw new Error(body.error || "Sign in failed")
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionOptions.queryKey }),
  })
  const submit = (event: FormEvent) => { event.preventDefault(); login.mutate() }

  return (
    <main className="login-screen">
      <div className="login-brand"><span className="brand-mark"><ScanText size={22} /></span><span>PageQuay</span></div>
      <div className="login-theme"><ThemeToggle /></div>
      <div className="login-panel">
        <div className="eyebrow">DOCUMENT WORKSPACE</div>
        <h1>Every document,<br />ready to use.</h1>
        <p>Sign in to extract text, process batches, and manage integrations.</p>
        <form onSubmit={submit} className="login-form">
          <label htmlFor="username">Username</label>
          <Input id="username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required />
          <label htmlFor="password">Password</label>
          <Input id="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
          {login.error && <p className="form-error" role="alert">{login.error.message}</p>}
          <Button type="submit" size="lg" disabled={login.isPending} className="mt-3 w-full justify-between">
            {login.isPending ? "Signing in…" : "Sign in"}<ArrowRight size={16} />
          </Button>
        </form>
      </div>
      <p className="login-foot">PageQuay © {new Date().getFullYear()}</p>
    </main>
  )
}

const links = [
  { to: "/", label: "Workbench" },
  { to: "/documents", label: "Documents" },
  { to: "/integrations", label: "Integrations" },
] as const

export function AppShell({ children, title, subtitle }: { children: ReactNode; title: string; subtitle: string }) {
  const session = useSession()
  const queryClient = useQueryClient()
  const pathname = useRouterState({ select: state => state.location.pathname })
  const logout = useMutation({
    mutationFn: async () => { await fetch("/api/session", { method: "DELETE" }) },
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(sessionOptions.queryKey, { authenticated: false })
    },
  })

  if (session.isPending) return <div className="loading-screen"><Skeleton className="h-8 w-48" /><Skeleton className="h-96 w-full max-w-4xl" /></div>
  if (session.isError) return <div className="loading-screen"><p role="alert">{session.error.message}</p><Button onClick={() => session.refetch()}>Try again</Button></div>
  if (!session.data?.authenticated) return <SignIn />

  return (
    <div className="app-frame">
      <header className="site-header">
        <div className="header-inner">
          <Link to="/" className="brand"><span className="brand-mark"><ScanText size={20} /></span><strong>PageQuay</strong></Link>
          <nav aria-label="Main navigation" className="site-nav">
            {links.map(({ to, label }) => <Link key={to} to={to} className={`nav-link ${pathname === to ? "active" : ""}`}>{label}</Link>)}
          </nav>
          <div className="header-actions"><ThemeToggle /><Button variant="outline" onClick={() => logout.mutate()}>Sign out <ArrowRight size={15} /></Button></div>
        </div>
      </header>
      <main className="page-content">
        <div className="page-heading"><div><p className="eyebrow">PAGEQUAY / DOCUMENT PROCESSING</p><h1>{title}</h1><p>{subtitle}</p></div></div>
        {children}
      </main>
    </div>
  )
}
