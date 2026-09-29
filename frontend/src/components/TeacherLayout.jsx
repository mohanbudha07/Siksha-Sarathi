import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import PortalLayout from './PortalLayout'

const groups = [
  { label: 'Overview', items: [
    { to: '/teacher/dashboard', label: 'Dashboard', icon: 'dashboard' },
  ] },
  { label: 'Teaching', items: [
    { to: '/teacher/notes', label: 'Learning Notes', icon: 'notes' },
    { to: '/teacher/quizzes', label: 'Quizzes', icon: 'quizzes' },
    { to: '/teacher/lab-quizzes', label: 'Lab Sessions', icon: 'lab' },
    { to: '/teacher/assessments', label: 'Paper Marks', icon: 'marks' },
  ] },
  { label: 'School Records', items: [
    { to: '/teacher/attendance', label: 'Attendance', icon: 'attendance' },
    { to: '/teacher/notices', label: 'Notices', icon: 'notices' },
    { to: '/teacher/chat', label: 'Chat', icon: 'chat' },
  ] },
  { label: 'Insights', items: [
    { to: '/teacher/analytics', label: 'Learning Insights', icon: 'insights' },
  ] },
]

function TeacherLayout({ children }) {
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
    try { await api.post('/logout') }
    catch (error) { console.error('Logout error:', error) }
    finally { navigate('/login') }
  }

  return <PortalLayout
    role="teacher"
    portalName="Teacher Workspace"
    homePath="/teacher/dashboard"
    groups={groups}
    unreadCount={unreadCount}
    onLogout={handleLogout}
  >{children}</PortalLayout>
}

export default TeacherLayout
