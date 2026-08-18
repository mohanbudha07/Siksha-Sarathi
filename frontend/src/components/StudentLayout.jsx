
import { NavLink, useNavigate } from 'react-router-dom'
import api from '../api'

function StudentLayout({ children }) {
  const navigate = useNavigate()

  const handleLogout = async () => {
    try {
      await api.get('/logout')
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      navigate('/login')
    }
  }

  return (
    <div>
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '15px 30px',
          background: '#2563eb',
          color: 'white',
        }}
      >
        <h2 style={{ margin: 0 }}>Siksha Sarathi</h2>

        <div
          style={{
            display: 'flex',
            gap: '10px',
            alignItems: 'center',
          }}
        >
          <NavLink to="/student/dashboard" style={linkStyle}>
            Dashboard
          </NavLink>

          <NavLink to="/student/performance" style={linkStyle}>
            Performance
          </NavLink>

          <NavLink to="/student/quiz" style={linkStyle}>
            Quizzes
          </NavLink>

          <NavLink to="/student/notes" style={linkStyle}>
            Notes
          </NavLink>

          <NavLink to="/student/ai" style={linkStyle}>
            AI Assistant
          </NavLink>

          <button
            onClick={handleLogout}
            style={{
              marginLeft: '10px',
              padding: '8px 14px',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Logout
          </button>
        </div>
      </nav>

      <main>{children}</main>
    </div>
  )
}

const linkStyle = ({ isActive }) => ({
  color: 'white',
  textDecoration: 'none',
  fontWeight: isActive ? 'bold' : 'normal',
  padding: '8px 10px',
  borderRadius: '6px',
})

export default StudentLayout
