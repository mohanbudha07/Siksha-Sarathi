import { useEffect, useRef } from 'react'

function ConfirmDialog({ confirmation, onCancel, onConfirm }) {
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)

  useEffect(() => {
    if (!confirmation) return undefined
    const previousFocus = document.activeElement
    cancelRef.current?.focus()
    return () => {
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
    }
  }, [confirmation])

  if (!confirmation) return null

  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onCancel()
      return
    }
    if (event.key !== 'Tab') return

    const focusable = dialogRef.current?.querySelectorAll(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
    if (!focusable?.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="feedback-dialog-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onCancel()
    }}>
      <section
        className="feedback-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-dialog-title"
        aria-describedby="feedback-dialog-description"
        ref={dialogRef}
        onKeyDown={handleKeyDown}
        tabIndex="-1"
      >
        <h2 id="feedback-dialog-title">{confirmation.title}</h2>
        <p id="feedback-dialog-description">{confirmation.description}</p>
        <div className="feedback-dialog-actions">
          <button type="button" className="feedback-dialog-cancel" ref={cancelRef} onClick={onCancel}>
            {confirmation.cancelLabel}
          </button>
          <button type="button" className={`feedback-dialog-confirm ${confirmation.variant === 'danger' ? 'is-danger' : ''}`} onClick={onConfirm}>
            {confirmation.confirmLabel}
          </button>
        </div>
      </section>
    </div>
  )
}

export default ConfirmDialog