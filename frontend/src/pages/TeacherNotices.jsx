import { useEffect, useState } from 'react'
import api from '../api'
import { notifyNoticeRead } from '../noticeEvents'
import { useToast } from '../components/feedback/useToast'
import './Notices.css'

const displayDate = (value) => value ? new Date(value).toLocaleString() : '—'

function TeacherNotices() {
  const { toast } = useToast()
  const [inbox, setInbox] = useState([])
  const [sent, setSent] = useState([])
  const [options, setOptions] = useState({ class_teacher_classes: [], subject_assignments: [], students: [] })
  const [unreadCount, setUnreadCount] = useState(0)
  const [audience, setAudience] = useState('class')
  const [classId, setClassId] = useState('')
  const [subjectAssignment, setSubjectAssignment] = useState('')
  const [studentId, setStudentId] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('inbox')

  const load = async () => {
    try {
      setLoading(true); setError('')
      const [inboxResponse, sentResponse, optionsResponse] = await Promise.all([
        api.get('/notices'), api.get('/notices/sent'), api.get('/teacher/notices/options'),
      ])
      setInbox(inboxResponse.data.notices || [])
      setUnreadCount(inboxResponse.data.unread_count || 0)
      setSent(sentResponse.data.notices || [])
      setOptions(optionsResponse.data)
      setClassId((value) => value || String(optionsResponse.data.class_teacher_classes[0]?.class_id || ''))
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
    } catch { toast.error('Unable to update notice status.') }
  }

  const createNotice = async (event) => {
    event.preventDefault()
    const payload = { title, body, visibility: 'internal', audience_type: audience }
    if (audience === 'class') payload.class_id = Number(classId)
    if (audience === 'subject') {
      const [assignedClassId, subjectId] = subjectAssignment.split(':')
      payload.class_id = Number(assignedClassId)
      payload.subject_id = Number(subjectId)
    }
    if (audience === 'student') payload.student_id = Number(studentId)
    try {
      setSaving(true); setError('')
      await api.post('/teacher/notices', payload)
      setTitle(''); setBody(''); toast.success('Notice published.')
      await load()
    } catch { toast.error('Unable to publish notice.') }
    finally { setSaving(false) }
  }

  return <div className="notice-page">
    <header className="notice-header"><div><p>CLASS COMMUNICATION</p><h1>Notices</h1><span>Internal, one-way announcements within your teaching scope.</span></div><div className="notice-unread-total"><strong>{unreadCount}</strong><span>Unread</span></div></header>
    {error && <div className="notice-error" role="alert">{error}</div>}
    <nav className="notice-view-tabs" role="tablist" aria-label="Notice views">
      {[['inbox', 'Inbox'], ['sent', 'Sent'], ['create', 'Create Notice']].map(([tab, label]) => <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)}>{label}</button>)}
    </nav>
    <section hidden={activeTab !== 'create'} className="notice-compose-section"><h2>Create Notice</h2><form className="notice-form" onSubmit={createNotice}>
      <label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength="200" required /></label>
      <label>Audience<select value={audience} onChange={(event) => { setAudience(event.target.value); setStudentId(''); setSubjectAssignment('') }}><option value="class" disabled={!options.class_teacher_classes.length}>My class</option><option value="subject" disabled={!options.subject_assignments.length}>Assigned class and subject</option><option value="student" disabled={!options.students.length}>Individual student I teach</option></select></label>
      {audience === 'class' && <label>Class<select value={classId} onChange={(event) => setClassId(event.target.value)} required><option value="">Select active class</option>{options.class_teacher_classes.map((item) => <option key={item.class_id} value={item.class_id}>{item.class_name} · {item.grade} / {item.section}</option>)}</select></label>}
      {audience === 'subject' && <label>Class and subject<select value={subjectAssignment} onChange={(event) => setSubjectAssignment(event.target.value)} required><option value="">Select assignment</option>{options.subject_assignments.map((item) => <option key={`${item.class_id}-${item.subject_id}`} value={`${item.class_id}:${item.subject_id}`}>{item.class_name} · {item.subject_name}</option>)}</select></label>}
      {audience === 'student' && <label>Student<select value={studentId} onChange={(event) => setStudentId(event.target.value)} required><option value="">Select eligible student</option>{options.students.map((item) => <option key={item.student_id} value={item.student_id}>{item.full_name} · {item.class_name}</option>)}</select></label>}
      <label className="notice-form-wide">Message<textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength="5000" rows="5" required /></label>
      <button type="submit" disabled={saving}>{saving ? 'Publishing...' : 'Publish Internal Notice'}</button>
    </form></section>
    <div className="notice-columns" hidden={activeTab === 'create'}>
      <section hidden={activeTab !== 'inbox'} className="notice-section"><h2>Inbox <span>{unreadCount} unread</span></h2>{loading ? <p className="notice-empty">Loading inbox...</p> : inbox.length === 0 ? <p className="notice-empty">No notices delivered to you.</p> : inbox.map((notice) => <article key={notice.id} className={`notice-item ${notice.is_read ? 'is-read' : 'is-unread'}`}><div className="notice-item-heading"><div><span className="notice-scope-label">{notice.audience_type}</span><h3>{notice.title}</h3></div><span className={`notice-state ${notice.is_read ? 'read' : 'unread'}`}>{notice.is_read ? 'Read' : 'Unread'}</span></div><p className="notice-body">{notice.body}</p><div className="notice-item-footer"><span>{notice.created_by} · {notice.created_by_role}</span><time>{displayDate(notice.created_at)}</time>{!notice.is_read && <button type="button" onClick={() => markRead(notice.id)}>Mark as read</button>}</div></article>)}</section>
      <section hidden={activeTab !== 'sent'} className="notice-section"><h2>Sent / Created</h2>{sent.length === 0 ? <p className="notice-empty">No notices published yet.</p> : sent.map((notice) => <article key={notice.id} className="notice-sent-item"><div className="notice-item-heading"><h3>{notice.title}</h3><span className="notice-scope-label">{notice.audience_type}</span></div><p>{notice.body}</p><small>{displayDate(notice.created_at)} · Delivered {notice.delivered_count} · Read {notice.read_count} · Unread {notice.unread_count}</small></article>)}</section>
    </div>
  </div>
}

export default TeacherNotices