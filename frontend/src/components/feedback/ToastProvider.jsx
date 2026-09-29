import { useCallback, useRef, useState } from 'react'
import FeedbackContext from './FeedbackContext'
import ToastViewport from './ToastViewport'
import ConfirmDialog from './ConfirmDialog'

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [confirmation, setConfirmation] = useState(null)
  const nextToastId = useRef(0)
  const confirmationResolver = useRef(null)

  const dismissToast = useCallback((id) => {
    setToasts((current) => current.filter((item) => item.id !== id))
  }, [])

  const pushToast = (type, message) => {
    const text = String(message || '').trim()
    if (!text) return
    const id = ++nextToastId.current
    setToasts((current) => {
      if (current.some((item) => item.type === type && item.message === text)) return current
      return [...current, { id, type, message: text }].slice(-4)
    })
  }

  const toast = {
    success: (message) => pushToast('success', message),
    error: (message) => pushToast('error', message),
    warning: (message) => pushToast('warning', message),
    info: (message) => pushToast('info', message),
  }

  const confirm = (options) => new Promise((resolve) => {
    if (confirmationResolver.current) confirmationResolver.current(false)
    confirmationResolver.current = resolve
    setConfirmation({
      title: options.title || 'Please confirm',
      description: options.description || '',
      confirmLabel: options.confirmLabel || 'Confirm',
      cancelLabel: options.cancelLabel || 'Cancel',
      variant: options.variant || 'default',
    })
  })

  const finishConfirmation = (result) => {
    confirmationResolver.current?.(result)
    confirmationResolver.current = null
    setConfirmation(null)
  }

  return (
    <FeedbackContext.Provider value={{ toast, confirm }}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismissToast} />
      <ConfirmDialog
        confirmation={confirmation}
        onCancel={() => finishConfirmation(false)}
        onConfirm={() => finishConfirmation(true)}
      />
    </FeedbackContext.Provider>
  )
}

export default ToastProvider