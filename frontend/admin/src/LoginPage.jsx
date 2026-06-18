import { useState } from 'react'
import { AlertCircle, WifiOff } from 'lucide-react'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'
const AGENT_URL = 'https://wavvy-agent.vercel.app'

const Y = '#f4f73d'

function validate(email, password) {
  if (!email.trim()) return 'Email is required.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'Enter a valid email address.'
  if (!password) return 'Password is required.'
  if (password.length < 6) return 'Password must be at least 6 characters.'
  return null
}

function ErrorBox({ error, type = 'auth' }) {
  if (!error) return null

  const isNetwork = type === 'network'
  const bg     = isNetwork ? 'rgba(250,188,45,0.10)' : 'rgba(252,83,91,0.10)'
  const border  = isNetwork ? 'rgba(250,188,45,0.25)' : 'rgba(252,83,91,0.25)'
  const color   = isNetwork ? '#fabc2d' : '#fc535b'
  const Icon    = isNetwork ? WifiOff : AlertCircle

  return (
    <div
      className="flex items-start gap-2.5 rounded-xl px-4 py-3 text-[13px] leading-relaxed"
      style={{ background: bg, border: `1px solid ${border}`, color }}
      role="alert"
    >
      <Icon size={15} className="shrink-0 mt-0.5" />
      <span>{error}</span>
    </div>
  )
}

export default function LoginPage({ onLogin }) {
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [errType,  setErrType]  = useState('auth')
  const [loading,  setLoading]  = useState(false)
  const [emailErr, setEmailErr] = useState(false)
  const [passErr,  setPassErr]  = useState(false)

  const showErr = (msg, type = 'auth') => {
    setError(msg)
    setErrType(type)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setEmailErr(false)
    setPassErr(false)

    const validErr = validate(email, password)
    if (validErr) {
      showErr(validErr)
      if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) setEmailErr(true)
      if (!password || password.length < 6) setPassErr(true)
      return
    }

    setLoading(true)
    try {
      const resp = await fetch(`${BACKEND}/api/auth/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email: email.trim(), password }),
        signal:  AbortSignal.timeout(15000),
      })

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        if (resp.status === 401) {
          showErr('Invalid email or password. Check your credentials and try again.')
          setEmailErr(true)
          setPassErr(true)
        } else {
          showErr(data.detail || `Server error (${resp.status}). Please try again.`)
        }
        return
      }

      const { token, user } = await resp.json()

      if (!['admin'].includes(user.role)) {
        showErr(
          `This account has "${user.role}" access, not admin. Use the Agent Console instead.`
        )
        return
      }

      localStorage.setItem('wavvy_admin_token', token)
      localStorage.setItem('wavvy_admin_info',  JSON.stringify(user))
      onLogin(user)

    } catch (err) {
      if (err.name === 'TimeoutError' || err.name === 'AbortError') {
        showErr(
          'The backend is taking too long to respond. HuggingFace Spaces can take ~30 seconds to wake up from sleep. Please wait and try again.',
          'network'
        )
      } else {
        showErr(
          'Could not reach the backend. It may be starting up — please wait ~30 seconds and try again.',
          'network'
        )
      }
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = (hasErr) => ({
    background: '#050505',
    border: `1px solid ${hasErr ? 'rgba(252,83,91,0.5)' : 'rgba(255,255,255,0.09)'}`,
    transition: 'border-color 0.15s',
  })

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
          <p className="text-[12px] text-white/25 uppercase tracking-[0.25em]">Admin Dashboard</p>
        </div>

        {/* Card */}
        <form
          onSubmit={handleSubmit}
          noValidate
          className="rounded-[24px] p-8 space-y-5"
          style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <div className="space-y-1 text-center">
            <h2 className="text-xl font-light text-white">Sign in</h2>
            <p className="text-[13px] text-white/25">Enter your admin credentials to continue</p>
          </div>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-[12px] uppercase tracking-widest font-semibold text-white/25">
                Email
              </label>
              <input
                type="email"
                autoFocus
                value={email}
                onChange={e => { setEmail(e.target.value); setEmailErr(false); setError('') }}
                placeholder="you@fin.ai"
                className="w-full rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none"
                style={inputStyle(emailErr)}
                onFocus={e => { if (!emailErr) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.22)' }}
                onBlur={e  => { if (!emailErr) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.09)' }}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-[12px] uppercase tracking-widest font-semibold text-white/25">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => { setPassword(e.target.value); setPassErr(false); setError('') }}
                placeholder="••••••••"
                className="w-full rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none"
                style={inputStyle(passErr)}
                onFocus={e => { if (!passErr) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.22)' }}
                onBlur={e  => { if (!passErr) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.09)' }}
              />
            </div>
          </div>

          <ErrorBox error={error} type={errType} />

          <button
            type="submit"
            disabled={loading}
            className="w-full font-bold uppercase text-[13px] tracking-widest py-4 rounded-full transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: Y, color: '#000' }}
          >
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        {/* Footer hint */}
        <p className="text-center text-[12px] text-white/20">
          Agent?{' '}
          <a href={AGENT_URL} className="text-white/40 hover:text-white/70 underline underline-offset-2 transition-colors">
            Open Agent Console
          </a>
        </p>
      </div>
    </div>
  )
}
