import { useState } from 'react'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import './AdminCsvManagement.css'

const sections = {
  students: {
    label: 'Students',
    template: '/admin/csv/templates/students',
    preview: '/admin/csv/students/preview',
    import: '/admin/csv/students/import',
    export: '/admin/csv/students/export',
    templateName: 'student_template.csv',
    exportName: 'students.csv',
    columns: [
      ['full_name', 'Name'], ['email', 'Email'], ['class_name', 'Class'],
      ['grade', 'Grade'], ['section', 'Section'],
    ],
  },
  teachers: {
    label: 'Teachers',
    template: '/admin/csv/templates/teachers',
    preview: '/admin/csv/teachers/preview',
    import: '/admin/csv/teachers/import',
    export: '/admin/csv/teachers/export',
    templateName: 'teacher_template.csv',
    exportName: 'teachers.csv',
    columns: [['full_name', 'Name'], ['email', 'Email']],
  },
  assignments: {
    label: 'Teacher Assignments',
    template: '/admin/csv/templates/teacher-assignments',
    preview: '/admin/csv/teacher-assignments/preview',
    import: '/admin/csv/teacher-assignments/import',
    export: '/admin/csv/teacher-assignments/export',
    templateName: 'teacher_assignment_template.csv',
    exportName: 'teacher_assignments.csv',
    columns: [
      ['teacher_email', 'Teacher email'], ['grade', 'Grade'],
      ['section', 'Section'], ['class_name', 'Class'],
      ['subject_code', 'Subject code'], ['subject_name', 'Subject'],
    ],
  },
}

async function responseError(error) {
  const payload = error.response?.data
  if (payload instanceof Blob) {
    try {
      return JSON.parse(await payload.text()).error || 'CSV request failed.'
    } catch { return 'CSV request failed.' }
  }
  return payload?.error || 'CSV request failed.'
}

function AdminCsvManagement() {
  const { toast } = useToast()
  const [active, setActive] = useState('students')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const config = sections[active]

  const selectSection = (key) => {
    setActive(key); setFile(null); setPreview(null)
    setError('')
  }

  const download = async (endpoint, fallbackName) => {
    try {
      setBusy('download'); setError('')
      const response = await api.get(endpoint, { responseType: 'blob' })
      const disposition = response.headers['content-disposition'] || ''
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName
      const objectUrl = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = objectUrl; link.download = filename
      document.body.appendChild(link); link.click(); link.remove()
      URL.revokeObjectURL(objectUrl)
    } catch { toast.error('Unable to download CSV.') }
    finally { setBusy('') }
  }

  const sendFile = async (endpoint) => {
    if (!file) throw new Error('Choose a CSV file first.')
    const formData = new FormData()
    formData.append('file', file)
    return api.post(endpoint, formData)
  }

  const validateFile = async () => {
    try {
      setBusy('preview'); setError(''); setPreview(null)
      const response = await sendFile(config.preview)
      setPreview(response.data)
      toast.info('CSV validation completed.')
    } catch (err) {
      if (err.response?.data?.rows) {
        setError(await responseError(err))
        setPreview(err.response.data)
      } else {
        toast.error('Unable to validate CSV file.')
      }
    } finally { setBusy('') }
  }

  const importFile = async () => {
    try {
      setBusy('import'); setError('')
      const response = await sendFile(config.import)
      const count = response.data.imported_students
        ?? response.data.imported_teachers
        ?? response.data.imported_assignments
        ?? 0
      const skipped = response.data.skipped_existing || 0
      toast.success(`Imported ${count} row${count === 1 ? '' : 's'}${skipped ? `; skipped ${skipped} existing assignment${skipped === 1 ? '' : 's'}` : ''}.`)
      setFile(null); setPreview(null)
    } catch (err) {
      if (err.response?.data?.rows) {
        setError(await responseError(err))
        setPreview(err.response.data)
      } else {
        toast.error('Unable to import CSV data.')
      }
    } finally { setBusy('') }
  }

  return <div className="admin-csv-page">
    <header className="admin-csv-heading"><div><p>ADMIN CONTROL</p><h1>CSV Management</h1><span>Preview every import before committing account or assignment changes.</span></div></header>
    {error && <div className="admin-csv-message error" role="alert">{error}</div>}
    <nav className="admin-csv-tabs" aria-label="CSV data type">
      {Object.entries(sections).map(([key, item]) => <button type="button" key={key} className={active === key ? 'active' : ''} aria-pressed={active === key} onClick={() => selectSection(key)}>{item.label}</button>)}
    </nav>
    <section className="admin-csv-workspace">
      <div className="admin-csv-actions">
        <button type="button" onClick={() => download(config.template, config.templateName)} disabled={Boolean(busy)}>Download Template</button>
        <button type="button" onClick={() => download(config.export, config.exportName)} disabled={Boolean(busy)}>Export Existing Data</button>
      </div>
      <div className="admin-csv-import">
        <label>CSV file<input type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setError('') }} /></label>
        <span>{file ? file.name : 'No file selected'}</span>
        <button type="button" onClick={validateFile} disabled={!file || Boolean(busy)}>{busy === 'preview' ? 'Validating...' : 'Validate / Preview'}</button>
        <button type="button" className="primary" onClick={importFile} disabled={!file || !preview?.valid || Boolean(busy)}>{busy === 'import' ? 'Importing...' : 'Import Valid Rows'}</button>
      </div>
      {preview && <section className="admin-csv-preview">
        <div className="admin-csv-preview-summary"><strong>{preview.total_rows} rows</strong><span>{preview.valid_rows} valid</span><span>{preview.invalid_rows} invalid</span>{preview.valid && <span className="all-valid">Ready to import</span>}</div>
        <div className="admin-csv-table-wrap"><table><thead><tr><th>Row</th>{config.columns.map(([, label]) => <th key={label}>{label}</th>)}<th>Status</th><th>Error</th></tr></thead><tbody>{preview.rows.map((row) => <tr key={row.row_number}><td>{row.row_number}</td>{config.columns.map(([key]) => <td key={key}>{row[key] || '—'}</td>)}<td>{row.errors.length ? 'Invalid' : row.status || 'Valid'}</td><td>{row.errors.map((item) => `${item.field}: ${item.message}`).join('; ') || '—'}</td></tr>)}</tbody></table></div>
      </section>}
    </section>
    <p className="admin-csv-footnote">Imports create new accounts and never update existing ones. Assignment rows marked “Already exists” are safely skipped. Passwords are hashed during import and are never included in preview or export.</p>
  </div>
}

export default AdminCsvManagement