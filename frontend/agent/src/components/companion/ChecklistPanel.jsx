import { Check, Circle } from 'lucide-react'

export default function ChecklistPanel({ checklist }) {
  if (!checklist?.length) return null

  return (
    <div className="flex flex-col gap-1.5">
      {checklist.map((item, i) => (
        <div key={i} className="flex items-start gap-2">
          {item.done ? (
            <Check size={14} color="#f4f73d" className="flex-shrink-0 mt-0.5" />
          ) : (
            <Circle size={14} color="#727781" className="flex-shrink-0 mt-0.5" />
          )}
          <span
            className="t-body-12"
            style={{ color: item.done ? '#727781' : '#ffffff' }}
          >
            {item.step}
          </span>
        </div>
      ))}
    </div>
  )
}
