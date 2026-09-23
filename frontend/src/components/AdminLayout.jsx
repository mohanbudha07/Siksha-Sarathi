import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import api from '../api'
import './AdminLayout.css'

const links = [
  { to: '/admin/dashboard', label: 'Dashboard' },
  { to: '/admin/users', label: 'User Management' },
  { to: '/admin/school-setup', label: 'School Setup' },
]

function AdminLayout({ children }) {
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
    <div className="admin-shell">
      <header className="admin-site-header">
        <NavLink className="admin-brand" to="/admin/dashboard">
          Siksha Sarathi <span>Admin</span>
        </NavLink>
        <button
          type="button"
          className="admin-menu-button"
          aria-label={menuOpen ? 'Close admin menu' : 'Open admin menu'}
          aria-expanded={menuOpen}
          aria-controls="admin-site-nav"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          {menuOpen ? '✕' : '☰'}
        </button>
        <nav
          id="admin-site-nav"
          className={`admin-site-nav ${menuOpen ? 'is-open' : ''}`}
          aria-label="Admin navigation"
        >
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => isActive
                ? 'admin-nav-link active'
                : 'admin-nav-link'}
              onClick={() => setMenuOpen(false)}
            >
              {link.label}
            </NavLink>
          ))}
          <button type="button" className="admin-logout" onClick={handleLogout}>
            Logout
          </button>
        </nav>
      </header>
      <main>{children}</main>
    </div>
  )
}

export default AdminLayout
