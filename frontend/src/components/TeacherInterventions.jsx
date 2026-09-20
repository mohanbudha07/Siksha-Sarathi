import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../api'
import './TeacherInterventions.css'

const reviewDate = () => {
  const date = new Date()
  date.setDate(date.getDate() + 14)
  return date.toISOString().slice(0, 10)
}

const emptyPlan = (subject) => ({
  subject,
  source_kind: 'manual',
  focus_area: '',
  evidence: '',
  action_plan: '',
  success_criteria: '',
  status: 'planned',
  review_date: reviewDate(),
  outcome_note: '',
})

function TeacherInterventions({ studentId, subject, suggestions }) {
  const [plans, setPlans] = useState([])
  const [draft, setDraft] = useState(() => emptyPlan(subject))
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadPlans = useCallback(async () => {
    try {
      setLoading(true)
      const response = await api.get(
        `/teacher/students/${studentId}/interventions`,
        { params: { subject } }
      )
      setPlans(response.data.interventions || [])
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load support plans.')
    } finally {
      setLoading(false)
    }
  }, [studentId, subject])

  useEffect(() => { loadPlans() }, [loadPlans])

  const activeCount = useMemo(
    () => plans.filter((item) => ['planned', 'in_progress'].includes(item.status)).length,
    [plans]
  )

  const beginPlan = (suggestion) => {
    setDraft({
      ...emptyPlan(subject),
      source_kind: suggestion?.kind || 'manual',
      focus_area: suggestion?.title || '',
      evidence: suggestion?.evidence || '',
      action_plan: suggestion?.suggestion || '',
    })
    setShowForm(true)
    setError(''); setMessage('')
  }

  const createPlan = async (event) => {
    event.preventDefault()
    try {
      setSaving(true); setError(''); setMessage('')
      await api.post(`/teacher/students/${studentId}/interventions`, draft)
      setDraft(emptyPlan(subject)); setShowForm(false)
      setMessage('Student support plan created.')
      await loadPlans()
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to create support plan.')
    } finally { setSaving(false) }
  }

  const changePlan = (id, field, value) => {
    setPlans((items) => items.map((item) =>
      item.id === id ? { ...item, [field]: value } : item
    ))
    setError(''); setMessage('')
  }

  const savePlan = async (plan) => {
    try {
      setSaving(true); setError(''); setMessage('')
      await api.put(`/teacher/interventions/${plan.id}`, plan)
      setMessage('Support plan progress updated.')
      await loadPlans()
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to update support plan.')
    } finally { setSaving(false) }
  }

  const deletePlan = async (plan) => {
    if (!window.confirm(`Delete the support plan “${plan.focus_area}”?`)) return
    try {
      setSaving(true); setError(''); setMessage('')
      await api.delete(`/teacher/interventions/${plan.id}`)
      setPlans((items) => items.filter((item) => item.id !== plan.id))
      setMessage('Support plan deleted.')
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to delete support plan.')
    } finally { setSaving(false) }
  }

  return (
    <section className="tla-panel intervention-panel">
      <div className="tla-section-heading intervention-heading">
        <div>
          <h2>Teacher support plans</h2>
          <p>Turn evidence into an action, review it, and record the outcome.</p>
        </div>
        <div><span>{activeCount} active</span><button onClick={() => beginPlan(null)}>+ Manual plan</button></div>
      </div>

      {error && <p className="intervention-message error" role="alert">{error}</p>}
      {message && <p className="intervention-message success">{message}</p>}

      {suggestions.length > 0 && <div className="intervention-suggestions">
        <h3>Evidence-based suggestions</h3>
        {suggestions.map((item, index) => <article key={`${item.kind}-${index}`}>
          <span className={`tla-action-kind tla-action-${item.kind}`}>{item.kind}</span>
          <div><strong>{item.title}</strong><small>{item.evidence}</small><p>{item.suggestion}</p></div>
          <button onClick={() => beginPlan(item)}>Create plan</button>
        </article>)}
      </div>}

      {showForm && <form className="intervention-form" onSubmit={createPlan}>
        <div className="intervention-form-title"><h3>New support plan</h3><button type="button" onClick={() => setShowForm(false)}>×</button></div>
        <label>Focus area<input value={draft.focus_area} maxLength="150" required onChange={(event) => setDraft({ ...draft, focus_area: event.target.value })} placeholder="Example: Force and motion concepts" /></label>
        <label>Evidence<textarea value={draft.evidence} maxLength="500" onChange={(event) => setDraft({ ...draft, evidence: event.target.value })} placeholder="What recorded evidence led to this plan?" /></label>
        <label>Teacher action<textarea value={draft.action_plan} minLength="10" maxLength="2000" required onChange={(event) => setDraft({ ...draft, action_plan: event.target.value })} placeholder="Describe the support activity." /></label>
        <label>Success criteria<textarea value={draft.success_criteria} maxLength="500" onChange={(event) => setDraft({ ...draft, success_criteria: event.target.value })} placeholder="How will you know the student improved?" /></label>
        <label>Review date<input type="date" value={draft.review_date} onChange={(event) => setDraft({ ...draft, review_date: event.target.value })} /></label>
        <button className="intervention-primary" disabled={saving}>{saving ? 'Saving...' : 'Create Support Plan'}</button>
      </form>}

      {loading ? <p className="tla-muted">Loading support plans...</p> : plans.length === 0 ? <p className="tla-muted">No support plan has been recorded for this student and subject.</p> : <div className="intervention-list">
        {plans.map((plan) => <article key={plan.id} className={`intervention-card status-${plan.status}`}>
          <div className="intervention-card-heading"><div><span>{plan.source_kind}</span><h3>{plan.focus_area}</h3><small>Review {plan.review_date || 'not scheduled'}</small></div><select value={plan.status} onChange={(event) => changePlan(plan.id, 'status', event.target.value)}><option value="planned">Planned</option><option value="in_progress">In progress</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></div>
          {plan.evidence && <p><strong>Evidence:</strong> {plan.evidence}</p>}
          <p><strong>Action:</strong> {plan.action_plan}</p>
          {plan.success_criteria && <p><strong>Success:</strong> {plan.success_criteria}</p>}
          <div className="intervention-edit-row"><label>Review date<input type="date" value={plan.review_date || ''} onChange={(event) => changePlan(plan.id, 'review_date', event.target.value)} /></label><label>Outcome / progress note<textarea value={plan.outcome_note || ''} maxLength="1000" onChange={(event) => changePlan(plan.id, 'outcome_note', event.target.value)} placeholder={plan.status === 'completed' ? 'Required before completion' : 'Add progress observed by the teacher'} /></label></div>
          <div className="intervention-card-actions"><button onClick={() => savePlan(plan)} disabled={saving}>Save progress</button><button className="danger" onClick={() => deletePlan(plan)} disabled={saving}>Delete</button></div>
        </article>)}
      </div>}
    </section>
  )
}

export default TeacherInterventions
