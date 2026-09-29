import { useEffect, useState } from 'react'
import api from '../api'
import { useToast } from './feedback/useToast'
import './ChatWorkspace.css'

const POLL_INTERVAL_MS = 4000

function mergeMessages(current, incoming) {
  const byId = new Map(current.map((message) => [message.id, message]))
  incoming.forEach((message) => byId.set(message.id, message))
  return [...byId.values()].sort((left, right) => left.id - right.id)
}

function formatTimestamp(value) {
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return String(value || '')
  return timestamp.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

function ChatWorkspace({ role }) {
  const { toast } = useToast()
  const [rooms, setRooms] = useState([])
  const [activeRoomId, setActiveRoomId] = useState(null)
  const [messages, setMessages] = useState([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingRooms, setLoadingRooms] = useState(true)
  const [currentUserId, setCurrentUserId] = useState(null)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [sending, setSending] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/auth/me')
      .then((response) => setCurrentUserId(response.data.user.id))
      .catch(() => setCurrentUserId(null))
  }, [])

  useEffect(() => {
    let cancelled = false
    api.get('/chat/rooms')
      .then((response) => {
        if (cancelled) return
        const availableRooms = response.data.rooms || []
        setRooms(availableRooms)
        setActiveRoomId((current) => availableRooms.some((room) => room.id === current)
          ? current
          : availableRooms[0]?.id ?? null)
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(requestError.response?.status === 401
            ? 'Your session has expired. Sign in again.'
            : 'Unable to load chat rooms.')
        }
      })
      .finally(() => { if (!cancelled) setLoadingRooms(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (activeRoomId === null) {
      setMessages([])
      setHasMore(false)
      return undefined
    }

    let cancelled = false
    let refreshing = false
    const roomEndpoint = `/chat/rooms/${activeRoomId}/messages`
    setMessages([])
    setHasMore(false)
    setLoadingMessages(true)

    const loseAccess = async () => {
      if (cancelled) return
      setActiveRoomId(null)
      setMessages([])
      setHasMore(false)
      setError('You no longer have access to this room.')
      try {
        const response = await api.get('/chat/rooms')
        setRooms(response.data.rooms || [])
      } catch {
        setRooms([])
      }
    }

    const loadLatest = async (initial = false) => {
      if (refreshing) return
      refreshing = true
      try {
        const response = await api.get(roomEndpoint)
        if (cancelled) return
        const result = response.data
        setMessages((current) => initial
          ? result.messages
          : mergeMessages(current, result.messages))
        setHasMore(result.has_more)
        setError('')
      } catch (requestError) {
        if (cancelled) return
        if (requestError.response?.status === 403) {
          await loseAccess()
        } else if (requestError.response?.status === 401) {
          setError('Your session has expired. Sign in again.')
        } else {
          setError('Unable to refresh this conversation. Check your connection.')
        }
      } finally {
        if (!cancelled && initial) setLoadingMessages(false)
        refreshing = false
      }
    }

    loadLatest(true)
    const intervalId = window.setInterval(() => loadLatest(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [activeRoomId])

  const activeRoom = rooms.find((room) => room.id === activeRoomId)

  const loadOlder = async () => {
    if (!activeRoom || !messages.length || loadingOlder) return
    setLoadingOlder(true)
    try {
      const response = await api.get(
        `/chat/rooms/${activeRoom.id}/messages`,
        { params: { before_id: messages[0].id } }
      )
      setMessages((current) => mergeMessages(response.data.messages, current))
      setHasMore(response.data.has_more)
    } catch (requestError) {
      if (requestError.response?.status === 403) {
        setActiveRoomId(null)
        setMessages([])
        setError('You no longer have access to this room.')
        api.get('/chat/rooms').then((response) => setRooms(response.data.rooms || []))
          .catch(() => setRooms([]))
      } else {
        setError(requestError.response?.status === 401
          ? 'Your session has expired. Sign in again.'
          : 'Unable to load earlier messages.')
      }
    } finally {
      setLoadingOlder(false)
    }
  }

  const sendMessage = async (event) => {
    event.preventDefault()
    if (!activeRoom || !draft.trim() || sending) return
    setSending(true)
    setError('')
    try {
      const response = await api.post(
        `/chat/rooms/${activeRoom.id}/messages`,
        { message: draft }
      )
      setMessages((current) => mergeMessages(current, [response.data.message]))
      setDraft('')
    } catch (requestError) {
      if (requestError.response?.status === 403) {
        setActiveRoomId(null)
        setMessages([])
        setError('You no longer have access to this room.')
        api.get('/chat/rooms').then((response) => setRooms(response.data.rooms || []))
          .catch(() => setRooms([]))
      } else if (requestError.response?.status === 401) {
        setError('Your session has expired. Sign in again.')
      } else {
        toast.error('Unable to send message.')
      }
    } finally {
      setSending(false)
    }
  }

  const groupedRooms = ['class', 'subject', 'staff'].map((type) => ({
    type,
    items: rooms.filter((room) => room.room_type === type),
  })).filter((group) => group.items.length)

  return (
    <div className="chat-workspace">
      <header className="chat-page-heading">
        <div>
          <p className="chat-eyebrow">SCHOOL COMMUNICATION</p>
          <h1>Chat</h1>
          <p>Room access follows current class and teaching assignments.</p>
        </div>
        <span className="chat-refresh-indicator">Updates every 4 seconds</span>
      </header>

      {error && <div className="chat-alert" role="alert">{error}</div>}

      <div className="chat-layout">
        <aside className="chat-room-sidebar" aria-label="Available chat rooms">
          <div className="chat-room-sidebar-heading">
            <h2>Rooms</h2>
            {!loadingRooms && <span>{rooms.length}</span>}
          </div>
          {loadingRooms && <p className="chat-empty-state">Loading rooms...</p>}
          {!loadingRooms && rooms.length === 0 && (
            <p className="chat-empty-state">No chat rooms are currently available.</p>
          )}
          {groupedRooms.map((group) => (
            <section className="chat-room-group" key={group.type}>
              <h3>{group.type}</h3>
              {group.items.map((room) => (
                <button
                  className={`chat-room-choice ${activeRoomId === room.id ? 'is-active' : ''}`}
                  key={room.id}
                  type="button"
                  aria-pressed={activeRoomId === room.id}
                  onClick={() => {
                    setMessages([])
                    setHasMore(false)
                    setActiveRoomId(room.id)
                    setError('')
                  }}
                >
                  <span>{room.name}</span>
                  <small>{room.room_type === 'class' ? 'Class room' : room.room_type === 'subject' ? room.subject_name : 'Institution-wide'}</small>
                </button>
              ))}
            </section>
          ))}
        </aside>

        <section className="chat-conversation" aria-label="Conversation">
          {activeRoom ? (
            <>
              <header className="chat-conversation-heading">
                <div>
                  <span className={`chat-room-type type-${activeRoom.room_type}`}>{activeRoom.room_type}</span>
                  <h2>{activeRoom.name}</h2>
                </div>
              </header>
              <div className="chat-message-history" aria-live="polite">
                {hasMore && (
                  <button className="chat-load-older" type="button" onClick={loadOlder} disabled={loadingOlder}>
                    {loadingOlder ? 'Loading...' : 'Load earlier messages'}
                  </button>
                )}
                {loadingMessages && messages.length === 0 && <p className="chat-empty-state">Loading messages...</p>}
                {!loadingMessages && messages.length === 0 && <p className="chat-empty-state">No messages yet. Start the conversation.</p>}
                {messages.map((message) => (
                  <article
                    className={`chat-message${message.sender.id === currentUserId ? ' is-own' : ''}`}
                    key={message.id}
                  >
                    <div className="chat-message-meta">
                      <strong>{message.sender.display_name}</strong>
                      <span>{message.sender.role}</span>
                      <time dateTime={message.created_at}>{formatTimestamp(message.created_at)}</time>
                    </div>
                    <p>{message.message}</p>
                  </article>
                ))}
              </div>
              <form className="chat-composer" onSubmit={sendMessage}>
                <label htmlFor="chat-message-input">Message</label>
                <textarea
                  id="chat-message-input"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  maxLength={2000}
                  rows={3}
                  placeholder="Write a message"
                  required
                />
                <div className="chat-composer-footer">
                  <span>{draft.length}/2000</span>
                  <button type="submit" disabled={!draft.trim() || sending}>
                    {sending ? 'Sending...' : 'Send message'}
                  </button>
                </div>
              </form>
            </>
          ) : (
            <div className="chat-no-room">
              <span aria-hidden="true">{role === 'admin' ? 'S' : 'C'}</span>
              <h2>{error ? 'Conversation unavailable' : 'Select a room'}</h2>
              <p>{error || 'Choose one of your available rooms to open its conversation.'}</p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

export default ChatWorkspace
