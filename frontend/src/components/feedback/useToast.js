import { useContext } from 'react'
import FeedbackContext from './FeedbackContext'

function useToast() {
  const context = useContext(FeedbackContext)
  if (!context) throw new Error('useToast must be used within ToastProvider')
  return context
}

export { useToast }
export default useToast