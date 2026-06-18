import { useState } from 'react'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

const Y  = '#f4f73d'
const Wa = (a) => `rgba(255,255,255,${a})`

export default function LoginPage({ onLogin }) {
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const resp = await fetch(`${BACKEND}/api/auth/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email, password }),
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        setError(data.detail || 'Invalid email or password')
        return
      }
      const { token, user } = await resp.json()
      if (user.role !== 'agent') {
        setError('Access denied. This portal is for agents only. Use the Admin Dashboard.')
        return
      }
      localStorage.setItem('wavvy_agent_token', token)
      localStorage.setItem('wavvy_agent_info',  JSON.stringify(user))
      onLogin(user)
    } catch {
      setError('Could not reach the server. Check your connection.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full min-h-screen bg-black text-white flex flex-col items-center justify-center font-sans px-4">
      <div className="w-full max-w-sm space-y-8">

        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="flex items-center justify-center gap-2">
            <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
              <path d="M4 16C4 16 7 24 12 24C17 24 15 8 20 8C25 8 28 16 28 16"
                stroke={Y} strokeWidth="3.5" strokeLinecap="round"/>
            </svg>
            <span className="text-lg font-semibold tracking-widest uppercase">
              Wavvy<span style={{ color: Y }}>.</span>
            </span>
          </div>
          <p className="text-[12px] text-white/25 uppercase tracking-[0.25em]">Agent Console</p>
        </div>

        {/* Card */}
        <form
          onSubmit={handleSubmit}
          className="rounded-[24px] p-8 space-y-5"
          style={{ background: Wa(0.025), border: `1px solid ${Wa(0.08)}` }}
        >
          <div className="space-y-1 text-center">
            <h2 className="text-xl font-light text-white">Sign in</h2>
            <p className="text-[13px] text-white/25">Enter your agent credentials to continue</p>
          </div>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-[12px] uppercase tracking-widest font-semibold text-white/25">Email</label>
              <input
                type="email"
                required
                autoFocus
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@fin.ai"
                className="w-full rounded-xl px-4 py-3 text-sm text-white placeholder-white/18 focus:outline-none transition-colors"
                style={{
                  background: '#050505',
                  border: `1px solid ${Wa(0.09)}`,
                }}
                onFocus={e => e.currentTarget.style.borderColor = Wa(0.22)}
                onBlur={e  => e.currentTarget.style.borderColor = Wa(0.09)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-[12px] uppercase tracking-widest font-semibold text-white/25">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-xl px-4 py-3 text-sm text-white placeholder-white/18 focus:outline-none transition-colors"
                style={{
                  background: '#050505',
                  border: `1px solid ${Wa(0.09)}`,
                }}
                onFocus={e => e.currentTarget.style.borderColor = Wa(0.22)}
                onBlur={e  => e.currentTarget.style.borderColor = Wa(0.09)}
              />
            </div>
          </div>

          {error && (
            <p className="text-[13px] text-white/70 text-center font-light">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full font-bold uppercase text-[13px] tracking-widest py-4 rounded-full transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: Y, color: '#000' }}
            onMouseEnter={e => { if (!loading) e.currentTarget.style.opacity = '0.9' }}
            onMouseLeave={e => { e.currentTarget.style.opacity = '1' }}
          >
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

      </div>
    </div>
  )
}
