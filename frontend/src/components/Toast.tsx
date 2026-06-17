import { useEffect, useRef } from 'react'

export interface ToastMessage {
  id: number
  message: string
  type: 'success' | 'error'
}

interface Props {
  toasts: ToastMessage[]
  onRemove: (id: number) => void
}

function ToastItem({ toast, onRemove }: { toast: ToastMessage; onRemove: (id: number) => void }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      if (ref.current) {
        ref.current.style.animation = 'slideOut 0.35s cubic-bezier(0.4, 0, 0.2, 1) forwards'
        setTimeout(() => onRemove(toast.id), 400)
      } else {
        onRemove(toast.id)
      }
    }, 3500)
    return () => clearTimeout(timer)
  }, [toast.id, onRemove])

  const icon = toast.type === 'success' ? '✅' : '⚠️'

  return (
    <div ref={ref} className={`toast toast-${toast.type}`}>
      <span style={{ fontSize: '1.1rem' }}>{icon}</span>
      <span>{toast.message}</span>
    </div>
  )
}

export function ToastCenter({ toasts, onRemove }: Props) {
  return (
    <div className="toast-center">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onRemove={onRemove} />
      ))}
    </div>
  )
}
