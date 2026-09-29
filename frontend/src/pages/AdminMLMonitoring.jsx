import { useEffect, useState } from 'react'
import api from '../api'
import '../styles/MLMonitoring.css'

function AdminMLMonitoring() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.get('/admin/ml/monitoring-status')
      .then((response) => {
        if (active) setReport(response.data)
      })
      .catch(() => {
        if (active) setError('Unable to load ML monitoring status.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  if (loading) {
    return <div className="ml-monitoring-page"><div className="ml-monitoring-state">Loading monitoring status...</div></div>
  }

  if (error) {
    return <div className="ml-monitoring-page"><div className="ml-monitoring-state is-error" role="alert">{error}</div></div>
  }

  const data = report || {}
  const monitoringState = data.monitoring_state || 'no_model'
  const status = data.status || 'model_unavailable'
  const available = Boolean(data.available)

  return (
    <div className="ml-monitoring-page">
      <header className="ml-monitoring-header">
        <p>ADMINISTRATION / MACHINE LEARNING</p>
        <h1>ML Monitoring</h1>
        <p>Monitoring reflects the current artifact state only. No synthetic model health is reported.</p>
      </header>
      <section className="ml-monitoring-grid" aria-label="Monitoring status">
        <div className="ml-monitoring-card"><strong>Status:</strong> {status}</div>
        <div className="ml-monitoring-card"><strong>Monitoring state:</strong> {monitoringState}</div>
        <div className="ml-monitoring-card"><strong>Artifact available:</strong> {available ? 'Yes' : 'No'}</div>
        <div className="ml-monitoring-card"><strong>Retraining required:</strong> {data.retraining_required ? 'Yes' : 'No'}</div>
        <div className="ml-monitoring-card"><strong>Reason:</strong> {data.reason || 'No validated production artifact is available.'}</div>
      </section>
    </div>
  )
}

export default AdminMLMonitoring
