import { Phone } from 'lucide-react'

export default function CallButton({ onClick }) {
  return (
    <button
      onClick={onClick}
      aria-label="Start a call"
      style={{
        position: 'fixed',
        bottom: '32px',
        right: '32px',
        width: '60px',
        height: '60px',
        borderRadius: '50%',
        background: '#f4f73d',
        border: 'none',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        animation: 'callPulse 2s ease-in-out infinite',
        zIndex: 9999,
      }}
    >
      <Phone size={24} color="#000000" />
    </button>
  )
}
