import { useEffect, useState } from 'react'
import api from '../api'

function AdminMLMonitoring() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api
      .get('/admin/ml/monitoring-status')
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
    return <div style={{ padding: '2rem' }}>Loading monitoring status...</div>
  }

  if (error) {
    return <div style={{ padding: '2rem', color: '#b91c1c' }}>{error}</div>
  }

  const data = report || {}
  const monitoringState = data.monitoring_state || 'no_model'
  const status = data.status || 'model_unavailable'
  const available = Boolean(data.available)

  return (
    <div style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
      <h1>ML Monitoring</h1>
      <p style={{ color: '#4b5563' }}>
        Monitoring reflects the current artifact state only. No synthetic model health is reported.
      </p>

      <div style={{ display: 'grid', gap: '1rem', marginTop: '1.5rem' }}>
        <div style={{ background: '#f3f4f6', borderRadius: '12px', padding: '1rem 1.25rem' }}>
          <strong>Status:</strong> {status}
        </div>
        <div style={{ background: '#f3f4f6', borderRadius: '12px', padding: '1rem 1.25rem' }}>
          <strong>Monitoring state:</strong> {monitoringState}
        </div>
        <div style={{ background: '#f3f4f6', borderRadius: '12px', padding: '1rem 1.25rem' }}>
          <strong>Artifact available:</strong> {available ? 'Yes' : 'No'}
        </div>
        <div style={{ background: '#f3f4f6', borderRadius: '12px', padding: '1rem 1.25rem' }}>
          <strong>Retraining required:</strong> {data.retraining_required ? 'Yes' : 'No'}
        </div>
        <div style={{ background: '#f3f4f6', borderRadius: '12px', padding: '1rem 1.25rem' }}>
          <strong>Reason:</strong> {data.reason || 'No validated production artifact is available.'}
        </div>
      </div>
    </div>
  )
}

export default AdminMLMonitoring
