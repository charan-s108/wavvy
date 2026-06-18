const Y  = '#f4f73d'
const Wa = (a) => `rgba(255,255,255,${a})`

export default function TopBar({ user, onLogout }) {
  return (
    <header className="glass h-[56px] flex items-center justify-between px-6 md:px-8 shrink-0 z-20">
      <div className="flex items-center gap-3.5">
        <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
          <path d="M4 16C4 16 7 24 12 24C17 24 15 8 20 8C25 8 28 16 28 16"
            stroke={Y} strokeWidth="3.5" strokeLinecap="round"/>
        </svg>
        <div className="flex items-center gap-2.5">
          <span className="font-semibold tracking-wider text-white" style={{ fontSize: 15 }}>
            Wavvy<span style={{ color: Y }}>.</span>
          </span>
          <span className="t-caps text-white/50 border border-white/[0.1] px-2.5 py-0.5 rounded-full" style={{ fontSize: 10 }}>
            Admin
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <p className="text-[13px] font-medium text-white leading-tight">{user.name}</p>
              <p className="text-[11px] text-white/40 leading-tight capitalize">{user.role}</p>
            </div>
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: `${Y}18`, border: `1.5px solid ${Y}40` }}
            >
              <span className="text-[13px] font-bold" style={{ color: Y }}>
                {user.name?.charAt(0)?.toUpperCase() ?? '?'}
              </span>
            </div>
          </div>
        )}

        {onLogout && (
          <button
            onClick={onLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-all"
            style={{
              color:  Wa(0.45),
              border: `1px solid ${Wa(0.08)}`,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.color            = Wa(0.9)
              e.currentTarget.style.borderColor      = Wa(0.20)
              e.currentTarget.style.backgroundColor  = Wa(0.05)
            }}
            onMouseLeave={e => {
              e.currentTarget.style.color            = Wa(0.45)
              e.currentTarget.style.borderColor      = Wa(0.08)
              e.currentTarget.style.backgroundColor  = 'transparent'
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            <span className="hidden sm:inline">Sign out</span>
          </button>
        )}
      </div>
    </header>
  )
}
