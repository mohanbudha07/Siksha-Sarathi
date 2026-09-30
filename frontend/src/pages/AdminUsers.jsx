import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import './AdminUsers.css'

const emptyAdminForm = { username: '', email: '', password: '' }
const emptyTeacherForm = { username: '', email: '', password: '' }
const emptyStudentForm = { full_name: '', email: '', password: '', class_id: '' }

const defaultPagination = { page: 1, page_size: 25, total: 0, total_pages: 0 }

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
  const { confirm, toast } = useToast()
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [classes, setClasses] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyForm, setBusyForm] = useState('')
  const [error, setError] = useState('')
  const [activeView, setActiveView] = useState('create')
  const [createRole, setCreateRole] = useState('student')
  const [listRole, setListRole] = useState('student')
  const [adminForm, setAdminForm] = useState(emptyAdminForm)
  const [teacherForm, setTeacherForm] = useState(emptyTeacherForm)
  const [studentForm, setStudentForm] = useState(emptyStudentForm)
  const [statusFilter, setStatusFilter] = useState('active')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [pagination, setPagination] = useState(defaultPagination)
  const [dialog, setDialog] = useState('')
  const [selectedUser, setSelectedUser] = useState(null)
  const [editForm, setEditForm] = useState({ username: '', full_name: '', email: '' })
  const [passwordForm, setPasswordForm] = useState({ temporary_password: '', confirmation: '' })
  const [transferForm, setTransferForm] = useState({ class_id: '', academic_year: '', transfer_note: '' })
  const [history, setHistory] = useState([])

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const setupResponse = await api.get('/admin/school-setup')
      setClasses(setupResponse.data.classes || [])
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load user management.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const loadUsers = useCallback(async () => {
    if (activeView !== 'list') return
    try {
      setLoading(true)
      setError('')
      const response = await api.get('/admin/accounts', {
        params: {
          role: listRole,
          status: statusFilter,
          search,
          page: pagination.page,
          page_size: pagination.page_size,
        },
      })
      setUsers(response.data.items || [])
      setPagination({
        page: response.data.page,
        page_size: response.data.page_size,
        total: response.data.total,
        total_pages: response.data.total_pages,
      })
    } catch (requestError) {
      setError(requestError.response?.data?.error || 'Unable to load account list.')
    } finally {
      setLoading(false)
    }
  }, [activeView, listRole, statusFilter, search, pagination.page, pagination.page_size])

  useEffect(() => { loadUsers() }, [loadUsers])

  const submit = async (formName, request, reset) => {
    try {
      setBusyForm(formName)
      setError('')
      await request()
      reset()
      toast.success(`${formName === 'admin' ? 'Administrator' : formName[0].toUpperCase() + formName.slice(1)} created.`)
      await loadData()
    } catch (requestError) {
      toast.error(requestError.response?.data?.error || `Unable to create ${formName === 'admin' ? 'administrator' : formName}.`)
    } finally {
      setBusyForm('')
    }
  }

  const openDialog = async (mode, user) => {
    setSelectedUser(user)
    setDialog(mode)
    if (mode === 'edit') setEditForm({
      username: user.username || '', full_name: user.full_name || '', email: user.email || '',
    })
    if (mode === 'transfer') setTransferForm({ class_id: '', academic_year: '', transfer_note: '' })
    if (mode === 'reset') setPasswordForm({ temporary_password: '', confirmation: '' })
    if (mode === 'view' || mode === 'history') {
      try {
        if (mode === 'history') {
          const response = await api.get(`/admin/students/${user.student_id}/enrollment-history`)
          setHistory(response.data.history || [])
        } else {
          const response = await api.get(`/admin/users/${user.user_id}`)
          setSelectedUser(response.data.user)
        }
      } catch (requestError) {
        toast.error(requestError.response?.data?.error || 'Unable to load account details.')
        setDialog('')
      }
    }
  }

  const saveEdit = async (event) => {
    event.preventDefault()
    try {
      setBusyForm('edit')
      const body = selectedUser.role === 'student'
        ? { full_name: editForm.full_name, email: editForm.email }
        : { username: editForm.username, email: editForm.email }
      const endpoint = selectedUser.role === 'student'
        ? `/admin/students/${selectedUser.student_id}`
        : `/admin/teachers/${selectedUser.user_id}`
      await api.put(endpoint, body)
      toast.success(`${selectedUser.role === 'student' ? 'Student' : 'Teacher'} account updated.`)
      setDialog('')
      await loadUsers()
    } catch (requestError) {
      toast.error(requestError.response?.data?.error || 'Unable to update account.')
    } finally { setBusyForm('') }
  }

  const submitTransfer = async (event) => {
    event.preventDefault()
    const target = classes.find((item) => String(item.id) === transferForm.class_id)
    if (!target) return
    const accepted = await confirm({
      title: `Transfer ${selectedUser.full_name} to ${target.name}?`,
      description: 'The current enrollment will be closed and a new enrollment period will be created. Previous enrollment history will be preserved.',
      confirmLabel: 'Transfer Student',
    })
    if (!accepted) return
    try {
      setBusyForm('transfer')
      await api.put(`/admin/students/${selectedUser.student_id}/class`, {
        class_id: Number(transferForm.class_id),
        academic_year: transferForm.academic_year,
        transfer_note: transferForm.transfer_note,
      })
      toast.success('Student transferred; enrollment history was preserved.')
      setDialog('')
      await loadUsers()
    } catch (requestError) {
      toast.error(requestError.response?.data?.error || 'Unable to transfer Student.')
    } finally { setBusyForm('') }
  }

  const resetPassword = async (event) => {
    event.preventDefault()
    if (passwordForm.temporary_password.length < 8 || !passwordForm.temporary_password.trim()) {
      toast.error('Temporary password must contain at least 8 non-whitespace characters.')
      return
    }
    if (passwordForm.temporary_password !== passwordForm.confirmation) {
      toast.error('Temporary passwords do not match.')
      return
    }
    if (!await confirm({
      title: 'Reset Temporary Password?',
      description: 'The user must change this password at next login.',
      confirmLabel: 'Reset Password',
    })) return
    try {
      setBusyForm('reset')
      await api.post(`/admin/users/${selectedUser.user_id}/reset-password`, {
        temporary_password: passwordForm.temporary_password,
      })
      toast.success('Temporary password reset. The user must change it at next login.')
      setPasswordForm({ temporary_password: '', confirmation: '' })
      setDialog('')
    } catch (requestError) {
      toast.error(requestError.response?.data?.error || 'Unable to reset password.')
    } finally { setBusyForm('') }
  }

  const changeAccountStatus = async (user) => {
    const isActive = Boolean(user.is_active)
    const name = user.full_name || user.username
    const roleName = user.role === 'student' ? 'Student' : 'Teacher'
    const accepted = await confirm({
      title: `${isActive ? 'Deactivate' : 'Reactivate'} ${name}?`,
      description: isActive
        ? user.role === 'student'
          ? 'This Student will no longer be able to sign in. Their quiz results, attendance, assessments, enrollment history and other school records will be preserved.'
          : 'This Teacher will no longer be able to sign in. Existing historical teaching and school records will be preserved.'
        : `The ${roleName} will be able to sign in again using their existing password, unless a temporary password reset is performed.`,
      confirmLabel: isActive ? 'Deactivate' : 'Reactivate',
      variant: isActive ? 'danger' : 'default',
    })
    if (!accepted) return
    try {
      setBusyForm('status')
      await api.post(`/admin/users/${user.user_id}/${isActive ? 'deactivate' : 'reactivate'}`)
      toast.success(`${roleName} account ${isActive ? 'deactivated' : 'reactivated'}.`)
      setDialog('')
      await loadUsers()
    } catch (requestError) {
      toast.error(requestError.response?.data?.error || 'Unable to update account status.')
    } finally { setBusyForm('') }
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

      <div className="admin-users-tabs" role="group" aria-label="User management view">
        <button type="button" className={activeView === 'create' ? 'active' : ''} aria-pressed={activeView === 'create'} onClick={() => { setError(''); setActiveView('create') }}>Create accounts</button>
        <button type="button" className={activeView === 'list' ? 'active' : ''} aria-pressed={activeView === 'list'} onClick={() => {
          setError(''); setListRole('student'); setStatusFilter('active');
          setSearch(''); setSearchInput(''); setPagination(defaultPagination);
          setActiveView('list')
        }}>Account list</button>
      </div>

      {activeView === 'create' ? (
        <>
          <div className="admin-users-tabs" role="group" aria-label="Account type">
            {[
              ['student', 'Student'], ['teacher', 'Teacher'], ['admin', 'Administrator'],
            ].map(([value, label]) => (
              <button type="button" key={value} className={createRole === value ? 'active' : ''} aria-pressed={createRole === value} onClick={() => setCreateRole(value)}>{label}</button>
            ))}
          </div>
          <section className="admin-users-form-grid" aria-label="Create account">
            {createRole === 'admin' && <AccountForm
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
            />}
            {createRole === 'teacher' && <AccountForm
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
            />}
            {createRole === 'student' && <AccountForm
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
            />}
          </section>
          {createRole === 'student' && classes.length === 0 && !loading && (
            <p className="admin-users-class-note">Create a class in School Setup before creating a student.</p>
          )}
        </>
      ) : (
        <>
          <div className="admin-users-tabs" role="group" aria-label="Account list role">
            {[
              ['student', 'Students'], ['teacher', 'Teachers'], ['admin', 'Administrators'],
            ].map(([value, label]) => (
              <button type="button" key={value} className={listRole === value ? 'active' : ''} aria-pressed={listRole === value} onClick={() => { setError(''); setListRole(value); setPagination((current) => ({ ...current, page: 1 })) }}>{label}</button>
            ))}
          </div>
          <section className="admin-users-list-controls" aria-label="Account list filters">
            <form className="admin-users-search" onSubmit={(event) => { event.preventDefault(); setPagination((current) => ({ ...current, page: 1 })); setSearch(searchInput.trim()) }}>
              <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search name or email" aria-label="Search name or email" />
              <button type="submit">Search</button>
            </form>
            <label>Status<select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPagination((current) => ({ ...current, page: 1 })) }}>
              <option value="active">Active</option><option value="inactive">Inactive</option><option value="all">All</option>
            </select></label>
          </section>
          {!loading && <section className="admin-users-list">
            <h2>{listRole === 'admin' ? 'Administrators' : listRole === 'teacher' ? 'Teachers' : 'Students'}</h2>
            {users.length === 0 ? <p className="admin-users-empty">No {listRole === 'admin' ? 'administrators' : `${listRole}s`} found.</p> : <div className="admin-users-records">
              {users.map((user) => <article className="admin-user-record" key={user.user_id}>
                <div className="admin-user-main">
                  <strong>{user.full_name || user.username}</strong>
                  <span>{user.email}</span>
                  {listRole === 'student' && <small>{user.class_name ? `${user.class_name} · Grade ${user.grade}` : `Grade ${user.grade || '—'} · No active class`}</small>}
                  {listRole === 'teacher' && <small>{user.assignment_count || 0} current assignment{user.assignment_count === 1 ? '' : 's'}</small>}
                </div>
                <div className="admin-user-status"><span className={user.is_active ? 'status-active' : 'status-inactive'}>{user.is_active ? 'Active' : 'Inactive'}</span><small>{user.created_at || '—'}</small></div>
                <div className="admin-user-actions">
                  {listRole !== 'admin' ? <>
                    <button type="button" onClick={() => openDialog('view', user)}>View</button>
                    <button type="button" onClick={() => openDialog('edit', user)}>Edit</button>
                    {listRole === 'student' && user.is_active && <button type="button" onClick={() => openDialog('transfer', user)}>Transfer</button>}
                    {listRole === 'teacher' && <button type="button" onClick={() => navigate('/admin/school-setup')}>Manage Assignments</button>}
                    <button type="button" onClick={() => openDialog('reset', user)}>Reset Password</button>
                    <button type="button" className={user.is_active ? 'danger' : ''} onClick={() => changeAccountStatus(user)}>{user.is_active ? 'Deactivate' : 'Reactivate'}</button>
                  </> : <span>Administrator</span>}
                </div>
              </article>)}
            </div>}
            {pagination.total_pages > 0 && <footer className="admin-users-pagination">
              <label>Rows per page<select value={pagination.page_size} onChange={(event) => setPagination((current) => ({ ...current, page_size: Number(event.target.value), page: 1 }))}>{[10, 25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
              <div><button type="button" disabled={pagination.page <= 1} onClick={() => setPagination((current) => ({ ...current, page: current.page - 1 }))}>← Previous</button><span>Page {pagination.page} of {pagination.total_pages}</span><button type="button" disabled={pagination.page >= pagination.total_pages} onClick={() => setPagination((current) => ({ ...current, page: current.page + 1 }))}>Next →</button></div>
            </footer>}
          </section>}
        </>
      )}

      {dialog && selectedUser && <div className="admin-users-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busyForm) setDialog('') }}>
        <section className="admin-users-dialog" role="dialog" aria-modal="true" aria-labelledby="account-dialog-title">
          <header><h2 id="account-dialog-title">{dialog === 'view' ? 'Account Details' : dialog === 'edit' ? `Edit ${selectedUser.role}` : dialog === 'transfer' ? 'Transfer Student' : dialog === 'history' ? 'Enrollment History' : 'Reset Temporary Password'}</h2><button type="button" aria-label="Close" disabled={Boolean(busyForm)} onClick={() => { setDialog(''); setPasswordForm({ temporary_password: '', confirmation: '' }) }}>×</button></header>
          {dialog === 'view' && <>
            <dl className="admin-account-details">
              <div><dt>Name</dt><dd>{selectedUser.full_name || selectedUser.username}</dd></div>
              <div><dt>Email</dt><dd>{selectedUser.email}</dd></div>
              <div><dt>Status</dt><dd>{selectedUser.is_active ? 'Active' : 'Inactive'}</dd></div>
              <div><dt>Created</dt><dd>{selectedUser.created_at || '—'}</dd></div>
              {!selectedUser.is_active && <div><dt>Deactivated</dt><dd>{selectedUser.deactivated_at || '—'}</dd></div>}
              {selectedUser.role === 'student' && <>
                <div><dt>Current Class</dt><dd>{selectedUser.class_name || 'No active enrollment'}</dd></div>
                <div><dt>Grade / Section</dt><dd>{selectedUser.grade || '—'} / {selectedUser.section || '—'}</dd></div>
                {selectedUser.academic_year && <div><dt>Academic Year</dt><dd>{selectedUser.academic_year}</dd></div>}
              </>}
              {selectedUser.role === 'teacher' && <div className="assignment-detail"><dt>Current assignments</dt><dd>{selectedUser.assignments?.length ? selectedUser.assignments.map((item) => <span key={`${item.class_id}-${item.subject_id}`}>{item.class_name} · {item.subject_name}</span>) : 'No current assignments'}</dd></div>}
            </dl>
            <div className="admin-users-dialog-actions">
              <button type="button" onClick={() => openDialog('edit', selectedUser)}>Edit</button>
              {selectedUser.role === 'student' && <>{selectedUser.is_active && <button type="button" onClick={() => openDialog('transfer', selectedUser)}>Transfer</button>}<button type="button" onClick={() => openDialog('history', selectedUser)}>Enrollment History</button></>}
              {selectedUser.role === 'teacher' && <button type="button" onClick={() => navigate('/admin/school-setup')}>Manage Assignments</button>}
              <button type="button" onClick={() => openDialog('reset', selectedUser)}>Reset Password</button>
              <button type="button" className={selectedUser.is_active ? 'danger' : ''} onClick={() => changeAccountStatus(selectedUser)}>{selectedUser.is_active ? 'Deactivate' : 'Reactivate'}</button>
            </div>
          </>}
          {dialog === 'edit' && <form className="admin-users-modal-form" onSubmit={saveEdit}>
            <label>{selectedUser.role === 'student' ? 'Full Name' : 'Name'}<input required maxLength="100" value={selectedUser.role === 'student' ? editForm.full_name : editForm.username} onChange={(event) => setEditForm((current) => selectedUser.role === 'student' ? { ...current, full_name: event.target.value } : { ...current, username: event.target.value })} /></label>
            <label>Email<input required type="email" maxLength="100" value={editForm.email} onChange={(event) => setEditForm((current) => ({ ...current, email: event.target.value }))} /></label>
            <p>Student class changes use the Transfer workflow to preserve enrollment history.</p>
            <footer><button type="button" onClick={() => setDialog('')}>Cancel</button><button type="submit" className="primary" disabled={Boolean(busyForm)}>{busyForm === 'edit' ? 'Saving…' : 'Save Changes'}</button></footer>
          </form>}
          {dialog === 'transfer' && <form className="admin-users-modal-form" onSubmit={submitTransfer}>
            <p>Current Class: <strong>{selectedUser.class_name || 'No active enrollment'}</strong></p>
            <label>New Class<select required value={transferForm.class_id} onChange={(event) => setTransferForm((current) => ({ ...current, class_id: event.target.value }))}><option value="">Select class</option>{classes.map((item) => <option value={item.id} key={item.id}>{item.name} · Grade {item.grade} / {item.section}</option>)}</select></label>
            <label>Academic Year (optional)<input maxLength="20" value={transferForm.academic_year} onChange={(event) => setTransferForm((current) => ({ ...current, academic_year: event.target.value }))} /></label>
            <label>Transfer Note (optional)<textarea maxLength="255" rows="2" value={transferForm.transfer_note} onChange={(event) => setTransferForm((current) => ({ ...current, transfer_note: event.target.value }))} /></label>
            <footer><button type="button" onClick={() => setDialog('')}>Cancel</button><button type="submit" className="primary" disabled={Boolean(busyForm)}>{busyForm === 'transfer' ? 'Transferring…' : 'Transfer Student'}</button></footer>
          </form>}
          {dialog === 'reset' && <form className="admin-users-modal-form" onSubmit={resetPassword}>
            <label>New temporary password<input required minLength="8" type="password" autoComplete="new-password" value={passwordForm.temporary_password} onChange={(event) => setPasswordForm((current) => ({ ...current, temporary_password: event.target.value }))} /></label>
            <label>Confirm temporary password<input required minLength="8" type="password" autoComplete="new-password" value={passwordForm.confirmation} onChange={(event) => setPasswordForm((current) => ({ ...current, confirmation: event.target.value }))} /></label>
            <p>The user must change this password at next login.</p>
            <footer><button type="button" onClick={() => { setDialog(''); setPasswordForm({ temporary_password: '', confirmation: '' }) }}>Cancel</button><button type="submit" className="primary" disabled={Boolean(busyForm)}>{busyForm === 'reset' ? 'Resetting…' : 'Reset Password'}</button></footer>
          </form>}
          {dialog === 'history' && <div className="admin-enrollment-history">
            {history.length === 0 ? <p>No enrollment history found.</p> : history.map((item) => <article key={item.id}>
              <div><strong>{item.class_name}</strong><span>Grade {item.grade} · Section {item.section}</span><b>{item.current ? 'Current' : 'Historical'}</b></div>
              <p>Academic Year: {item.academic_year || '—'}</p><p>Started: {item.started_at || '—'}</p><p>Ended: {item.ended_at || '—'}</p><p>Transfer Note: {item.transfer_note || '—'}</p>
            </article>)}
            <footer><button type="button" onClick={() => setDialog('')}>Close</button></footer>
          </div>}
        </section>
      </div>}
    </div>
  )
}

export default AdminUsers
