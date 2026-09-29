import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import PortalLayout from './PortalLayout'

const groups = [
  { label: 'Overview', items: [
    { to: '/admin/dashboard', label: 'Dashboard', icon: 'dashboard' },
  ] },
  { label: 'People', items: [
    { to: '/admin/users', label: 'User Management', icon: 'users' },
  ] },
  { label: 'School', items: [
    { to: '/admin/school-setup', label: 'School Setup', icon: 'school' },
    { to: '/admin/attendance', label: 'Attendance', icon: 'attendance' },
    { to: '/admin/notices', label: 'Notices', icon: 'notices' },
    { to: '/admin/chat', label: 'Chat', icon: 'chat' },
  ] },
  { label: 'Data', items: [
    { to: '/admin/csv', label: 'CSV Management', icon: 'csv' },
  ] },
  { label: 'Intelligence', items: [
    { to: '/admin/ml-readiness', label: 'ML Readiness', icon: 'insights' },
    { to: '/admin/ml-monitoring', label: 'ML Monitoring', icon: 'insights' },
  ] },
]

function AdminLayout({ children }) {
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
      navigate('/admin/login')
    }
  }

  return <PortalLayout
    role="admin"
    portalName="Administration"
    homePath="/admin/dashboard"
    groups={groups}
    unreadCount={unreadCount}
    onLogout={handleLogout}
  >{children}</PortalLayout>
}

export default AdminLayout
