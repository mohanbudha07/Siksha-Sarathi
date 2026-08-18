import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')

    try {
      await api.post('/login', {
        email,
        password,
      })

      navigate('/student/dashboard')
    } catch (error) {
      console.error(error)

      setError(
        error.response?.data?.error ||
          'Login failed. Please try again.'
      )
    }
  }

  return (
    <div>
      <h1>Siksha Sarathi</h1>
      <h2>Student Login</h2>

      <form onSubmit={handleSubmit}>
        <div>
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>

        <div>
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>

        {error && <p>{error}</p>}

        <button type="submit">Login</button>
      </form>
    </div>
  )
}

export default Login
