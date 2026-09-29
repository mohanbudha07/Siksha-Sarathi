import { useEffect } from 'react'

const durations = {
  success: 3500,
  info: 4000,
  warning: 5000,
  error: 6000,
}

function ToastItem({ item, onDismiss }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(item.id), durations[item.type])
    return () => window.clearTimeout(timer)
  }, [item.id, item.type, onDismiss])

  return (
    <div className={`feedback-toast toast-${item.type}`} role={item.type === 'error' ? 'alert' : 'status'} aria-live={item.type === 'error' ? 'assertive' : 'polite'} aria-atomic="true">
      <span className="feedback-toast-mark" aria-hidden="true" />
      <p>{item.message}</p>
      <button type="button" aria-label="Dismiss notification" onClick={() => onDismiss(item.id)}>×</button>
    </div>
  )
}

function ToastViewport({ toasts, onDismiss }) {
  return (
    <div className="feedback-toast-viewport" aria-label="Notifications">
      {toasts.map((item) => <ToastItem key={item.id} item={item} onDismiss={onDismiss} />)}
    </div>
  )
}

export default ToastViewport