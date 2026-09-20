import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './StudentRegister.css'

function StudentRegister() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    username: '',
    full_name: '',
    email: '',
    class_id: '',
    password: '',
    confirm_password: '',
  })

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [classes, setClasses] = useState([])

  useEffect(() => {
    api.get('/public/classes')
      .then((response) => setClasses(response.data.classes || []))
      .catch(() => setError('Unable to load available classes.'))
  }, [])

  const handleChange = (event) => {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')

    if (form.password !== form.confirm_password) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)

    try {
      await api.post('/register', {
        username: form.username,
        full_name: form.full_name,
        email: form.email,
        class_id: Number(form.class_id),
        password: form.password,
        role: 'student',
      })

      navigate('/login', { state: { notice: 'Student account created. You can sign in now.' } })
    } catch (error) {
      setError(
        error.response?.data?.error ||
          'Registration failed. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="student-register-page">
      <section className="student-register-card">
      <div><p>SIKSHA SARATHI</p><h1>Create Student Account</h1><span>Select your school class so your teacher can see your learning records.</span></div>

      <form onSubmit={handleSubmit}>
        <label>Full name
        <input
          name="full_name"
          placeholder="Full Name"
          value={form.full_name}
          onChange={handleChange}
          required
        />
        </label>

        <label>Username
        <input
          name="username"
          placeholder="Username"
          value={form.username}
          onChange={handleChange}
          required
        />
        </label>

        <label>Email
        <input
          name="email"
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={handleChange}
          required
        />
        </label>

        <label>Class
          <select name="class_id" value={form.class_id} onChange={handleChange} required>
            <option value="">Select your class</option>
            {classes.map((item) => <option key={item.id} value={item.id}>{item.name} — Grade {item.grade}{item.section && item.section !== 'Default' ? ` (${item.section})` : ''}</option>)}
          </select>
        </label>

        <label>Password
        <input
          name="password"
          type="password"
          placeholder="Password"
          value={form.password}
          onChange={handleChange}
          minLength="8"
          required
        />
        </label>

        <label>Confirm password
        <input
          name="confirm_password"
          type="password"
          placeholder="Confirm Password"
          value={form.confirm_password}
          onChange={handleChange}
          minLength="8"
          required
        />
        </label>

        {error && <p>{error}</p>}

        <button type="submit" disabled={loading}>
          {loading ? 'Creating Account...' : 'Create Student Account'}
        </button>
      </form>

      <p>
        Already have an account?{' '}
        <button onClick={() => navigate('/login')}>
          Sign In
        </button>
      </p>
      </section>
    </div>
  )
}

export default StudentRegister
