import { useEffect, useState } from 'react'
import api from '../api'
import { notifyNoticeRead } from '../noticeEvents'
import { useToast } from '../components/feedback/useToast'
import './Notices.css'

const displayDate = (value) => value ? new Date(value).toLocaleString() : '—'

function StudentNotices() {
  const { toast } = useToast()
  const [notices, setNotices] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      setLoading(true); setError('')
      const response = await api.get('/notices')
      setNotices(response.data.notices || [])
      setUnreadCount(response.data.unread_count || 0)
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load notices.')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const markRead = async (noticeId) => {
    try {
      await api.patch(`/notices/${noticeId}/read`)
      setNotices((items) => items.map((item) => item.id === noticeId
        ? { ...item, is_read: true, read_at: new Date().toISOString() }
        : item))
      setUnreadCount((count) => Math.max(0, count - 1))
      notifyNoticeRead()
    } catch { toast.error('Unable to update notice status.') }
  }

  return <div className="notice-page">
    <header className="notice-header"><div><p>OFFICIAL UPDATES</p><h1>Notices</h1><span>One-way announcements from your institution.</span></div><div className="notice-unread-total"><strong>{unreadCount}</strong><span>Unread</span></div></header>
    {error && <div className="notice-error" role="alert">{error}</div>}
    {loading ? <div className="notice-empty">Loading notices...</div> : notices.length === 0 ? <div className="notice-empty"><strong>No notices yet</strong><span>New official notices delivered to you will appear here.</span></div> : <section className="notice-list" aria-label="Your notices">
      {notices.map((notice) => <article key={notice.id} className={`notice-item ${notice.is_read ? 'is-read' : 'is-unread'}`}>
        <div className="notice-item-heading"><div><span className="notice-scope-label">{notice.audience_type}</span><h2>{notice.title}</h2></div><span className={`notice-state ${notice.is_read ? 'read' : 'unread'}`}>{notice.is_read ? 'Read' : 'Unread'}</span></div>
        <p className="notice-body">{notice.body}</p>
        <div className="notice-item-footer"><span>From {notice.created_by} · {notice.created_by_role}</span><time dateTime={notice.created_at}>{displayDate(notice.created_at)}</time>{!notice.is_read && <button type="button" onClick={() => markRead(notice.id)}>Mark as read</button>}</div>
      </article>)}
    </section>}
  </div>
}

export default StudentNotices