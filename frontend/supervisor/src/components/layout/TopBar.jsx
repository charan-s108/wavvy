const Y = '#f4f73d'

export default function TopBar() {
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

      <div className="flex items-center gap-2.5">
        <span className="t-caps text-white/45 hidden sm:block" style={{ fontSize: 11 }}>Admin Dashboard</span>
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: Y, boxShadow: `0 0 5px rgba(244,247,61,0.7)` }}
        />
      </div>
    </header>
  )
}
