import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import PortalLayout from './PortalLayout'

const groups = [
  { label: 'Overview', items: [
    { to: '/student/dashboard', label: 'Dashboard', icon: 'dashboard' },
  ] },
  { label: 'Learning', items: [
    { to: '/student/practice-plan', label: 'My Plan', icon: 'plan' },
    { to: '/student/quiz', label: 'Quizzes', icon: 'quizzes' },
    { to: '/student/notes', label: 'Learning Materials', icon: 'notes' },
    { to: '/student/ai', label: 'AI Assistant', icon: 'ai' },
  ] },
  { label: 'School', items: [
    { to: '/student/attendance', label: 'Attendance', icon: 'attendance' },
    { to: '/student/notices', label: 'Notices', icon: 'notices' },
    { to: '/student/chat', label: 'Chat', icon: 'chat' },
  ] },
]

function StudentLayout({ children }) {
  const navigate = useNavigate()
  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    const loadUnreadCount = () => api.get('/notices/unread-count')
      .then((response) => setUnreadCount(Number(response.data.unread_count) || 0))
      .catch(() => setUnreadCount(0))
    loadUnreadCount()
    window.addEventListener('notice-read', loadUnreadCount)
    return () => window.removeEventListener('notice-read', loadUnreadCount)
  }, [])

  const handleLogout = async () => {
    try {
      await api.post('/logout')
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      navigate('/login')
    }
  }

  return <PortalLayout
    role="student"
    portalName="Student Portal"
    homePath="/student/dashboard"
    groups={groups}
    unreadCount={unreadCount}
    onLogout={handleLogout}
  >{children}</PortalLayout>
}

export default StudentLayout
