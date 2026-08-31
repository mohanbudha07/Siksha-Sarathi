import { NavLink, useNavigate } from 'react-router-dom'
import api from '../api'

function TeacherLayout({ children }) {
  const navigate = useNavigate()

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
    <div className="teacher-layout">
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '15px 30px',
          background: 'linear-gradient(135deg, #4f00ff, #6d00e8)',
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
          <NavLink to="/teacher/dashboard" style={linkStyle}>
            Dashboard
          </NavLink>

          <NavLink to="/teacher/notes" style={linkStyle}>
            My Notes
          </NavLink>

          <button
            onClick={handleLogout}
            style={{
              marginLeft: '10px',
              padding: '8px 14px',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              background: 'white',
              color: '#4f00ff',
              fontWeight: '600',
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

export default TeacherLayout