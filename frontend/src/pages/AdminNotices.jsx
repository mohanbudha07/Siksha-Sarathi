import { useEffect, useState } from 'react'
import api from '../api'
import { notifyNoticeRead } from '../noticeEvents'
import './Notices.css'

const displayDate = (value) => value ? new Date(value).toLocaleString() : '—'

function AdminNotices() {
  const [options, setOptions] = useState({ classes: [], students: [], teachers: [] })
  const [inbox, setInbox] = useState([])
  const [sent, setSent] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [visibility, setVisibility] = useState('internal')
  const [audience, setAudience] = useState('all')
  const [target, setTarget] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = async () => {
    try {
      setLoading(true); setError('')
      const [optionsResponse, inboxResponse, sentResponse] = await Promise.all([
        api.get('/admin/notices/options'), api.get('/notices'), api.get('/notices/sent'),
      ])
      setOptions(optionsResponse.data)
      setInbox(inboxResponse.data.notices || [])
      setUnreadCount(inboxResponse.data.unread_count || 0)
      setSent(sentResponse.data.notices || [])
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load notice tools.')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const markRead = async (noticeId) => {
    try {
      await api.patch(`/notices/${noticeId}/read`)
      setInbox((items) => items.map((item) => item.id === noticeId
        ? { ...item, is_read: true, read_at: new Date().toISOString() }
        : item))
      setUnreadCount((count) => Math.max(0, count - 1))
      notifyNoticeRead()
    } catch (err) { setError(err.response?.data?.error || 'Unable to update notice status.') }
  }

  const createNotice = async (event) => {
    event.preventDefault()
    const payload = { title, body, visibility, audience_type: audience }
    if (audience === 'class') payload.class_id = Number(target)
    if (audience === 'student') payload.student_id = Number(target)
    if (audience === 'teacher') payload.teacher_user_id = Number(target)
    try {
      setSaving(true); setError(''); setSuccess('')
      const response = await api.post('/admin/notices', payload)
      setSuccess(`Notice published to ${response.data.delivered_count} recipient${response.data.delivered_count === 1 ? '' : 's'}.`)
      setTitle(''); setBody(''); setTarget('')
      await load()
    } catch (err) { setError(err.response?.data?.error || 'Unable to publish notice.') }
    finally { setSaving(false) }
  }

  const targetOptions = audience === 'class' ? options.classes.map((item) => ({ id: item.id, label: `${item.name} · ${item.grade} / ${item.section}` }))
    : audience === 'student' ? options.students.map((item) => ({ id: item.student_id, label: `${item.full_name}${item.class_name ? ` · ${item.class_name}` : ''}` }))
      : options.teachers.map((item) => ({ id: item.teacher_user_id, label: item.username }))

  return <div className="notice-page">
    <header className="notice-header"><div><p>INSTITUTIONAL COMMUNICATION</p><h1>Notices</h1><span>Publish official announcements and review delivery.</span></div><div className="notice-unread-total"><strong>{unreadCount}</strong><span>Unread</span></div></header>
    {error && <div className="notice-error" role="alert">{error}</div>}{success && <div className="notice-success" role="status">{success}</div>}
    <section className="notice-compose-section"><h2>Create Notice</h2><form className="notice-form" onSubmit={createNotice}>
      <label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength="200" required /></label>
      <label>Visibility<select value={visibility} onChange={(event) => { const value = event.target.value; setVisibility(value); if (value === 'public') setAudience('all'); setTarget('') }}><option value="internal">Internal</option><option value="public">Public</option></select></label>
      <label>Audience<select value={audience} disabled={visibility === 'public'} onChange={(event) => { setAudience(event.target.value); setTarget('') }}><option value="all">Entire institution</option><option value="students">All students</option><option value="teachers">All teachers</option><option value="class">Specific class</option><option value="student">Specific student</option><option value="teacher">Specific teacher</option></select></label>
      {audience !== 'all' && audience !== 'students' && audience !== 'teachers' && <label>Target<select value={target} onChange={(event) => setTarget(event.target.value)} required><option value="">Select target</option>{targetOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>}
      <label className="notice-form-wide">Message<textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength="5000" rows="5" required /></label>
      <button type="submit" disabled={saving}>{saving ? 'Publishing...' : 'Publish Notice'}</button>
    </form></section>
    <div className="notice-columns">
      <section className="notice-section"><h2>Inbox <span>{unreadCount} unread</span></h2>{loading ? <p className="notice-empty">Loading inbox...</p> : inbox.length === 0 ? <p className="notice-empty">No notices delivered to your account.</p> : inbox.map((notice) => <article key={notice.id} className={`notice-item ${notice.is_read ? 'is-read' : 'is-unread'}`}><div className="notice-item-heading"><div><span className="notice-scope-label">{notice.audience_type}</span><h3>{notice.title}</h3></div><span className={`notice-state ${notice.is_read ? 'read' : 'unread'}`}>{notice.is_read ? 'Read' : 'Unread'}</span></div><p className="notice-body">{notice.body}</p><div className="notice-item-footer"><span>{notice.created_by} · {notice.created_by_role}</span><time>{displayDate(notice.created_at)}</time>{!notice.is_read && <button type="button" onClick={() => markRead(notice.id)}>Mark as read</button>}</div></article>)}</section>
      <section className="notice-section"><h2>Sent / Created</h2>{sent.length === 0 ? <p className="notice-empty">No notices published yet.</p> : sent.map((notice) => <article key={notice.id} className="notice-sent-item"><div className="notice-item-heading"><h3>{notice.title}</h3><span className="notice-scope-label">{notice.visibility} · {notice.audience_type}</span></div><p>{notice.body}</p><small>{displayDate(notice.created_at)} · Delivered {notice.delivered_count} · Read {notice.read_count} · Unread {notice.unread_count}</small></article>)}</section>
    </div>
  </div>
}

export default AdminNotices