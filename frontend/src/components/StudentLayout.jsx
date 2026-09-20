import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import api from '../api'
import './StudentLayout.css'

const links = [
  { to: '/student/dashboard', label: 'Dashboard' },
  { to: '/student/practice-plan', label: 'My Plan' },
  { to: '/student/quiz', label: 'Quizzes' },
  { to: '/student/notes', label: 'Notes' },
  { to: '/student/ai', label: 'AI Assistant' },
]

function StudentLayout({ children }) {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  const handleLogout = async () => {
    try {
      await api.post('/logout')
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      navigate('/login')
    }
  }

  return (
    <div className="student-shell">
      <header className="student-site-header">
        <NavLink className="student-brand" to="/student/dashboard">Siksha Sarathi</NavLink>
        <button
          className="student-menu-button"
          type="button"
          aria-label={menuOpen ? 'Close student menu' : 'Open student menu'}
          aria-expanded={menuOpen}
          aria-controls="student-site-nav"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          {menuOpen ? '✕' : '☰'}
        </button>
        <nav id="student-site-nav" className={`student-site-nav ${menuOpen ? 'is-open' : ''}`} aria-label="Student navigation">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to}
              className={({ isActive }) => isActive ? 'student-nav-link active' : 'student-nav-link'}
              onClick={() => setMenuOpen(false)}>
              {link.label}
            </NavLink>
          ))}
          <button type="button" className="student-logout" onClick={handleLogout}>Logout</button>
        </nav>
      </header>
      <main>{children}</main>
    </div>
  )
}

export default StudentLayout
