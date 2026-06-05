import { LayoutDashboard, Phone, History, Star, GraduationCap, BookOpen, Settings } from 'lucide-react'

const NAV_ITEMS = [
  { id: 'overview',  label: 'Overview',   Icon: LayoutDashboard },
  { id: 'live',      label: 'Live Calls', Icon: Phone },
  { id: 'history',   label: 'History',    Icon: History },
  { id: 'qa',        label: 'QA Scores',  Icon: Star },
  { id: 'coaching',  label: 'Coaching',   Icon: GraduationCap },
  { id: 'knowledge', label: 'Knowledge',  Icon: BookOpen },
  { id: 'settings',  label: 'Settings',   Icon: Settings },
]

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function SideNav({ active, onNavigate }) {
  return (
    <nav
      className="w-[220px] flex-shrink-0 flex flex-col py-4 overflow-y-auto"
      style={{ background: '#040404', borderRight: `1px solid ${Wa(0.05)}` }}
    >
      <div className="flex flex-col gap-0.5 px-2.5">
        {NAV_ITEMS.map(({ id, label, Icon }) => {
          const isActive = active === id
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className="flex items-center gap-3 px-3 py-3 rounded-xl transition-all text-left w-full"
              style={{
                background: isActive ? Ya(0.08) : 'transparent',
                borderLeft: isActive ? `2px solid ${Y}` : '2px solid transparent',
                paddingLeft: isActive ? 10 : 12,
              }}
              onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = Wa(0.03) }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent' }}
            >
              <Icon size={16} color={isActive ? Y : Wa(0.42)} strokeWidth={isActive ? 2 : 1.5} />
              <span
                className="text-[14px] font-medium"
                style={{ color: isActive ? '#fff' : Wa(0.52) }}
              >
                {label}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
