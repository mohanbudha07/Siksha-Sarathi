import { useCallback, useEffect, useState } from 'react'
import api from '../api'
import './AdminUsers.css'

const emptyAdminForm = { username: '', email: '', password: '' }
const emptyTeacherForm = { username: '', email: '', password: '' }
const emptyStudentForm = { full_name: '', email: '', password: '', class_id: '' }

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

function UserTable({ columns, rows, emptyMessage }) {
  if (rows.length === 0) return <p className="admin-users-empty">{emptyMessage}</p>

  return (
    <div className="admin-users-table-wrap">
      <table className="admin-users-table">
        <thead>
          <tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.user_id || row.id}>
              {columns.map((column) => (
                <td key={column.key}>{column.render ? column.render(row) : row[column.key] || '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AccountForm({ title, fields, form, setForm, onSubmit, busy, submitLabel }) {
  return (
    <form className="admin-users-form" onSubmit={onSubmit}>
      <h2>{title}</h2>
      {fields.map((field) => (
        <label key={field.name}>
          {field.label}
          {field.type === 'select' ? (
            <select
              value={form[field.name]}
              onChange={(event) => setForm({ ...form, [field.name]: event.target.value })}
              required
              disabled={busy || field.disabled}
            >
              <option value="">Select class</option>
              {field.options.map((option) => (
                <option key={option.id} value={option.id}>{option.name}</option>
              ))}
            </select>
          ) : (
            <input
              type={field.type || 'text'}
              value={form[field.name]}
              onChange={(event) => setForm({ ...form, [field.name]: event.target.value })}
              minLength={field.minLength}
              required
              disabled={busy}
            />
          )}
        </label>
      ))}
      <button type="submit" disabled={busy || fields.some((field) => field.disabled)}>
        {busy ? 'Saving...' : submitLabel}
      </button>
    </form>
  )
}

function AdminUsers() {
  const [users, setUsers] = useState({ admins: [], teachers: [], students: [] })
  const [classes, setClasses] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyForm, setBusyForm] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [adminForm, setAdminForm] = useState(emptyAdminForm)
  const [teacherForm, setTeacherForm] = useState(emptyTeacherForm)
  const [studentForm, setStudentForm] = useState(emptyStudentForm)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const [usersResponse, setupResponse] = await Promise.all([
        api.get('/admin/users'),
        api.get('/admin/school-setup'),
      ])
      setUsers(usersResponse.data)
      setClasses(setupResponse.data.classes || [])
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load user management.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const submit = async (formName, request, reset) => {
    try {
      setBusyForm(formName)
      setError('')
      setSuccess('')
      await request()
      reset()
      setSuccess('Account created successfully.')
      await loadData()
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to create this account.')
    } finally {
      setBusyForm('')
    }
  }

  const adminFields = [
    { name: 'username', label: 'Name' },
    { name: 'email', label: 'Email', type: 'email' },
    { name: 'password', label: 'Temporary password', type: 'password', minLength: 8 },
  ]
  const teacherFields = adminFields
  const studentFields = [
    { name: 'full_name', label: 'Full name' },
    { name: 'email', label: 'Email', type: 'email' },
    { name: 'password', label: 'Temporary password', type: 'password', minLength: 8 },
    { name: 'class_id', label: 'Class', type: 'select', options: classes, disabled: classes.length === 0 },
  ]

  return (
    <div className="admin-users-page">
      <section className="admin-users-hero">
        <p>ADMIN CONTROL</p>
        <h1>User Management</h1>
        <span>Create and review the accounts in this school.</span>
      </section>

      {loading && <div className="admin-users-message">Loading users...</div>}
      {error && <div className="admin-users-message error" role="alert">{error}</div>}
      {success && <div className="admin-users-message success" role="status">{success}</div>}

      <section className="admin-users-form-grid" aria-label="Create accounts">
        <AccountForm
          title="Create administrator"
          fields={adminFields}
          form={adminForm}
          setForm={setAdminForm}
          busy={busyForm === 'admin'}
          submitLabel="Create Administrator"
          onSubmit={(event) => {
            event.preventDefault()
            submit('admin', () => api.post('/admin/admins', adminForm), () => setAdminForm(emptyAdminForm))
          }}
        />
        <AccountForm
          title="Create teacher"
          fields={teacherFields}
          form={teacherForm}
          setForm={setTeacherForm}
          busy={busyForm === 'teacher'}
          submitLabel="Create Teacher"
          onSubmit={(event) => {
            event.preventDefault()
            submit('teacher', () => api.post('/admin/teachers', teacherForm), () => setTeacherForm(emptyTeacherForm))
          }}
        />
        <AccountForm
          title="Create student"
          fields={studentFields}
          form={studentForm}
          setForm={setStudentForm}
          busy={busyForm === 'student'}
          submitLabel="Create Student"
          onSubmit={(event) => {
            event.preventDefault()
            submit('student', () => api.post('/admin/students', {
              ...studentForm,
              class_id: Number(studentForm.class_id),
            }), () => setStudentForm(emptyStudentForm))
          }}
        />
      </section>
      {classes.length === 0 && !loading && (
        <p className="admin-users-class-note">Create a class in School Setup before creating a student.</p>
      )}

      {!loading && (
        <div className="admin-users-lists">
          <section className="admin-users-list">
            <h2>Administrators</h2>
            <UserTable
              rows={users.admins}
              emptyMessage="No administrators found."
              columns={[
                { key: 'username', label: 'Name' },
                { key: 'email', label: 'Email' },
                { key: 'created_at', label: 'Created', render: (row) => formatDate(row.created_at) },
              ]}
            />
          </section>
          <section className="admin-users-list">
            <h2>Teachers</h2>
            <UserTable
              rows={users.teachers}
              emptyMessage="No teachers found."
              columns={[
                { key: 'username', label: 'Name' },
                { key: 'email', label: 'Email' },
                { key: 'created_at', label: 'Created', render: (row) => formatDate(row.created_at) },
              ]}
            />
          </section>
          <section className="admin-users-list">
            <h2>Students</h2>
            <UserTable
              rows={users.students}
              emptyMessage="No students found."
              columns={[
                { key: 'full_name', label: 'Full name' },
                { key: 'email', label: 'Email' },
                { key: 'grade', label: 'Grade' },
                { key: 'class_name', label: 'Class' },
                { key: 'created_at', label: 'Created', render: (row) => formatDate(row.created_at) },
              ]}
            />
          </section>
        </div>
      )}
    </div>
  )
}

export default AdminUsers
