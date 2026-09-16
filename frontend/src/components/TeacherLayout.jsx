import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherLayout.css'

const navigation = [
  { label: 'Overview', items: [{ to: '/teacher/dashboard', icon: '⌂', label: 'Dashboard' }] },
  { label: 'Teaching', items: [
    { to: '/teacher/notes', icon: 'N', label: 'Learning Notes' },
    { to: '/teacher/quizzes', icon: 'Q', label: 'Quizzes' },
    { to: '/teacher/lab-quizzes', icon: 'L', label: 'Lab Sessions' },
  ] },
  { label: 'School records', items: [
    { to: '/teacher/assessments', icon: 'M', label: 'Paper Marks' },
    { to: '/teacher/attendance', icon: 'A', label: 'Attendance' },
  ] },
  { label: 'Insights', items: [{ to: '/teacher/analytics', icon: 'I', label: 'Learning Insights' }] },
]

function TeacherLayout({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => { setMenuOpen(false) }, [location.pathname])

  const handleLogout = async () => {
    try { await api.post('/logout') }
    catch (error) { console.error('Logout error:', error) }
    finally { navigate('/login') }
  }

  return (
    <div className="teacher-shell">
      <header className="teacher-mobile-header">
        <button className="teacher-menu-button" onClick={() => setMenuOpen(true)} aria-label="Open teacher navigation">☰</button>
        <div><strong>Siksha Sarathi</strong><span>Teacher workspace</span></div>
      </header>
      {menuOpen && <button className="teacher-nav-overlay" onClick={() => setMenuOpen(false)} aria-label="Close teacher navigation" />}
      <aside className={`teacher-sidebar ${menuOpen ? 'is-open' : ''}`}>
        <div className="teacher-brand">
          <span>SS</span><div><strong>Siksha Sarathi</strong><small>Teacher workspace</small></div>
          <button onClick={() => setMenuOpen(false)} aria-label="Close teacher navigation">×</button>
        </div>
        <nav className="teacher-navigation" aria-label="Teacher navigation">
          {navigation.map((group) => (
            <section key={group.label}>
              <p>{group.label}</p>
              {group.items.map((item) => (
                <NavLink key={item.to} to={item.to} className={({ isActive }) => `teacher-nav-link ${isActive ? 'active' : ''}`}>
                  <span>{item.icon}</span>{item.label}
                </NavLink>
              ))}
            </section>
          ))}
        </nav>
        <div className="teacher-sidebar-footer">
          <div><span>T</span><div><strong>Teacher account</strong><small>Secure workspace</small></div></div>
          <button onClick={handleLogout}>Log out</button>
        </div>
      </aside>
      <main className="teacher-shell-content">{children}</main>
    </div>
  )
}

export default TeacherLayout
