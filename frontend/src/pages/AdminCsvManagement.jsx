import { useRef, useState } from 'react'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import './AdminCsvManagement.css'

const sections = {
  students: {
    label: 'Students',
    description: 'Create multiple Student accounts and enroll them in existing classes.',
    entity: 'Students',
    template: '/admin/csv/templates/students',
    preview: '/admin/csv/students/preview',
    import: '/admin/csv/students/import',
    export: '/admin/csv/students/export',
    templateName: 'student_template.csv',
    exportName: 'students.csv',
    referenceDownloads: [['/admin/csv/references/classes', 'Download Class Reference', 'class_reference.csv']],
    columns: [
      ['Full Name', "Student's full name."],
      ['Email', 'Must be unique across Siksha Sarathi.'],
      ['Temporary Password', 'At least 8 characters; Students change it after first login.'],
      ['Grade', 'Must match an existing Grade.'],
      ['Section', 'Must exist for the selected Grade.'],
      ['Academic Year', 'Optional. Example: 2083/84.'],
    ],
    example: [
      ['Full Name', 'Aarav Sharma'], ['Email', 'aarav@example.com'],
      ['Temporary Password', 'Example only: TempPass123'], ['Grade', '10'],
      ['Section', 'A'], ['Academic Year', '2083/84'],
    ],
    previewColumns: [['full_name', 'Name'], ['email', 'Email'], ['grade', 'Grade'], ['section', 'Section']],
  },
  teachers: {
    label: 'Teachers',
    description: 'Create multiple Teacher accounts with temporary passwords.',
    entity: 'Teachers',
    template: '/admin/csv/templates/teachers',
    preview: '/admin/csv/teachers/preview',
    import: '/admin/csv/teachers/import',
    export: '/admin/csv/teachers/export',
    templateName: 'teacher_template.csv',
    exportName: 'teachers.csv',
    columns: [
      ['Full Name', "Teacher's full name."],
      ['Email', 'Must be unique across Siksha Sarathi.'],
      ['Temporary Password', 'At least 8 characters; Teachers change it after first login.'],
    ],
    example: [
      ['Full Name', 'Mira Thapa'], ['Email', 'mira@example.com'],
      ['Temporary Password', 'Example only: TempPass123'],
    ],
    previewColumns: [['full_name', 'Name'], ['email', 'Email']],
  },
  assignments: {
    label: 'Teacher Assignments',
    description: 'Assign existing Teachers to Classes and Subjects in bulk.',
    entity: 'Assignments',
    template: '/admin/csv/templates/teacher-assignments',
    preview: '/admin/csv/teacher-assignments/preview',
    import: '/admin/csv/teacher-assignments/import',
    export: '/admin/csv/teacher-assignments/export',
    templateName: 'teacher_assignment_template.csv',
    exportName: 'teacher_assignments.csv',
    referenceDownloads: [
      ['/admin/csv/references/classes', 'Download Class Reference', 'class_reference.csv'],
      ['/admin/csv/references/subjects', 'Download Subject Reference', 'subject_reference.csv'],
    ],
    columns: [
      ['Teacher Email', 'The Teacher account must already exist.'],
      ['Grade', 'Must match an existing Class.'],
      ['Section', 'Must match an existing Class for that Grade.'],
      ['Subject Code', 'Must exactly match an existing Subject code.'],
    ],
    example: [
      ['Teacher Email', 'mira@example.com'], ['Grade', '10'],
      ['Section', 'A'], ['Subject Code', 'SCI'],
    ],
    previewColumns: [['teacher_email', 'Teacher email'], ['grade', 'Grade'], ['section', 'Section'], ['subject_code', 'Subject code']],
  },
}

const fieldLabels = {
  _row: 'Row', full_name: 'Full Name', email: 'Email', temporary_password: 'Temporary Password',
  grade: 'Grade', section: 'Section', academic_year: 'Academic Year',
  teacher_email: 'Teacher Email', subject_code: 'Subject Code',
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
  const { confirm, toast } = useToast()
  const fileInputRef = useRef(null)
  const [active, setActive] = useState('students')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [fileError, setFileError] = useState('')
  const [showColumns, setShowColumns] = useState(false)
  const [showErrors, setShowErrors] = useState(false)
  const [visibleErrorRows, setVisibleErrorRows] = useState(10)
  const [showValidRows, setShowValidRows] = useState(false)
  const [visibleValidRows, setVisibleValidRows] = useState(10)
  const [dragging, setDragging] = useState(false)
  const config = sections[active]

  const selectSection = (key) => {
    if (busy === 'import') return
    setActive(key); setFile(null); setPreview(null); setFileError('')
    setError('')
    setShowColumns(false); setShowErrors(false); setShowValidRows(false)
    setVisibleErrorRows(10); setVisibleValidRows(10)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const download = async (endpoint, fallbackName, label) => {
    try {
      setBusy('download'); setError('')
      const response = await api.get(endpoint, { responseType: 'blob' })
      const disposition = response.headers['content-disposition'] || ''
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName
      const objectUrl = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = objectUrl; link.download = filename
      document.body.appendChild(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
      toast.success(`${label} downloaded.`)
    } catch { toast.error(`Unable to download ${label.toLowerCase()}.`) }
    finally { setBusy('') }
  }

  const chooseFile = (nextFile) => {
    if (busy) return
    setPreview(null); setError(''); setFileError('')
    if (!nextFile) {
      setFile(null)
      return
    }
    if (!nextFile.name.toLowerCase().endsWith('.csv')) {
      setFile(null); setFileError('Only CSV files are accepted.')
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }
    if (nextFile.size > 5 * 1024 * 1024) {
      setFile(null); setFileError('CSV files must be 5 MB or smaller.')
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }
    setFile(nextFile)
    setShowErrors(false); setShowValidRows(false)
    setVisibleErrorRows(10); setVisibleValidRows(10)
  }

  const sendFile = async (endpoint) => {
    if (!file) throw new Error('Choose a CSV file first.')
    const formData = new FormData()
    formData.append('file', file)
    return api.post(endpoint, formData)
  }

  const validateFile = async () => {
    if (!file || busy) return
    try {
      setBusy('preview'); setError(''); setPreview(null)
      const response = await sendFile(config.preview)
      setPreview(response.data)
      setShowErrors(false); setShowValidRows(false)
      setVisibleErrorRows(10); setVisibleValidRows(10)
    } catch (err) {
      if (err.response?.data?.rows) {
        setPreview(err.response.data)
      } else {
        setFileError(await responseError(err) || 'Unable to check CSV file.')
      }
    } finally { setBusy('') }
  }

  const importFile = async () => {
    if (busy || !preview?.valid) return
    const count = active === 'assignments' ? preview.new_rows : preview.valid_rows
    if (!count) return
    const title = `Import ${count} ${config.entity}?`
    const description = active === 'students'
      ? `This will create ${count} new Student accounts and enroll them in their classes.`
      : active === 'teachers'
        ? `This will create ${count} new Teacher accounts.`
        : `This will create ${count} new Teacher Assignments.${preview.skipped_existing ? ` ${preview.skipped_existing} existing assignments will be skipped.` : ''}`
    if (!await confirm({ title, description, confirmLabel: 'Import' })) return
    try {
      setBusy('import'); setError('')
      const response = await sendFile(config.import)
      const imported = response.data.imported_students
        ?? response.data.imported_teachers
        ?? response.data.imported_assignments
        ?? 0
      const skipped = response.data.skipped_existing || 0
      const successMessage = active === 'students'
        ? `${imported} Students imported successfully.`
        : active === 'teachers'
          ? `${imported} Teachers imported successfully.`
          : `${imported} assignments imported successfully${skipped ? `; ${skipped} existing assignments skipped` : ''}.`
      toast.success(successMessage)
      setFile(null); setPreview(null); setFileError(''); setShowErrors(false); setShowValidRows(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      if (err.response?.data?.rows) {
        setPreview(err.response.data)
      } else {
        toast.error(await responseError(err) || 'Unable to import CSV data.')
      }
    } finally { setBusy('') }
  }

  const downloadTemplate = () => download(config.template, config.templateName, `${config.label} template`)
  const downloadExport = () => download(config.export, config.exportName, `${config.label} export`)
  const validPreviewRows = (preview?.rows || []).filter((row) => !row.errors?.length)
  const invalidPreviewRows = (preview?.rows || []).filter((row) => row.errors?.length)
  const importCount = active === 'assignments' ? preview?.new_rows || 0 : preview?.valid_rows || 0

  const renderRowLabel = (row) => {
    const detail = config.previewColumns
      .map(([key, label]) => row[key] ? `${label}: ${row[key]}` : '')
      .filter(Boolean)
    return detail.join(' · ')
  }

  return <div className="admin-csv-page">
    <header className="admin-csv-heading"><div><p>ADMIN CONTROL</p><h1>CSV Management</h1><span>Prepare and check bulk records before importing them into your school.</span></div></header>
    {error && <div className="admin-csv-message error" role="alert">{error}</div>}
    <nav className="admin-csv-tabs" aria-label="CSV data type" aria-disabled={busy === 'import'}>
      {Object.entries(sections).map(([key, item]) => <button type="button" key={key} className={active === key ? 'active' : ''} aria-pressed={active === key} disabled={busy === 'import'} onClick={() => selectSection(key)}>{item.label}</button>)}
    </nav>
    <p className="admin-csv-description">{config.description}</p>
    <ol className="admin-csv-steps"><li>Download the template</li><li>Fill it in using Excel or Google Sheets</li><li>Upload the completed CSV</li></ol>
    <section className="admin-csv-workspace">
      <div className="admin-csv-tool-grid">
        <section className="admin-csv-template-card">
          <div><h2>CSV Template</h2><p>Start with the official Siksha Sarathi template.</p></div>
          <button type="button" onClick={downloadTemplate} disabled={Boolean(busy)}>Download Template</button>
          {config.referenceDownloads?.length > 0 && <div className="admin-csv-reference-actions">{config.referenceDownloads.map(([endpoint, label, filename]) => <button type="button" key={endpoint} onClick={() => download(endpoint, filename, label.replace('Download ', ''))} disabled={Boolean(busy)}>{label}</button>)}</div>}
          <button type="button" className="admin-csv-columns-toggle" aria-expanded={showColumns} onClick={() => setShowColumns((current) => !current)}>{showColumns ? 'Hide required columns' : 'View required columns'}</button>
          {showColumns && <dl className="admin-csv-column-list">{config.columns.map(([label, description]) => <div key={label}><dt>{label}</dt><dd>{description}</dd></div>)}</dl>}
          {config.example && <div className="admin-csv-example"><strong>Example</strong>{config.example.map(([label, value]) => <p key={label}><span>{label}</span>{value}</p>)}{active !== 'assignments' && <small>Example password only; do not reuse it for real accounts.</small>}</div>}
        </section>
        <section className="admin-csv-export-card">
          <h2>Export</h2><p>Download current records for this section.</p>
          <button type="button" onClick={downloadExport} disabled={Boolean(busy)}>{active === 'students' ? 'Export Students' : active === 'teachers' ? 'Export Teachers' : 'Export Assignments'}</button>
        </section>
      </div>
      <div className="admin-csv-import">
        <div
          className={`admin-csv-dropzone ${dragging ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
          onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true) }}
          onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }}
          onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files?.[0]) }}
        >
          <strong>{file ? '✓ CSV file selected' : 'Upload CSV File'}</strong>
          {!file && <><span>Drag and drop a CSV here</span><span>or</span></>}
          <label className="admin-csv-choose-file">{file ? 'Change File' : 'Choose CSV File'}
            <input ref={fileInputRef} type="file" accept=".csv,text/csv" disabled={Boolean(busy)} onChange={(event) => { chooseFile(event.target.files?.[0]); event.target.value = '' }} />
          </label>
          <small>{file ? <span className="admin-csv-filename" title={file.name}>{file.name}</span> : 'CSV only · Maximum 5 MB'}</small>
        </div>
        {fileError && <p className="admin-csv-message error" role="alert">{fileError}</p>}
        <p className="admin-csv-limit-note">Maximum 5 MB and 5,000 data rows per file.</p>
        <p className="admin-csv-all-or-nothing">Imports are all-or-nothing: fix every problem before importing. Existing Teacher Assignments are safely skipped.</p>
        {preview && <section className={`admin-csv-preview ${preview.valid ? 'is-valid' : 'is-invalid'}`}>
          {preview.valid ? <h2>✓ File is ready to import</h2> : <h2>⚠ File needs attention</h2>}
          <div className="admin-csv-preview-summary">
            <strong>{preview.total_rows} rows found</strong>
            {active === 'assignments' ? <><span>{preview.new_rows} new assignments</span><span>{preview.skipped_existing} already exist</span></> : <span>{preview.valid_rows} ready</span>}
            <span>{preview.invalid_rows} problems</span>
          </div>
          {!preview.valid && <p className="admin-csv-blocked-copy">Fix all problems before importing. No records have been created.</p>}
          {preview.valid && validPreviewRows.length > 0 && <section className="admin-csv-valid-preview"><h3>Preview</h3>
            {validPreviewRows.slice(0, showValidRows ? visibleValidRows : 10).map((row) => <article key={row.row_number}><strong>Row {row.row_number}</strong><span>{renderRowLabel(row)}</span>{row.status === 'Already exists' && <b>Already exists</b>}</article>)}
            {validPreviewRows.length > (showValidRows ? visibleValidRows : 10) && <button type="button" className="admin-csv-text-button" onClick={() => { setShowValidRows(true); setVisibleValidRows((count) => Math.min(50, count + 10)) }}>Show more</button>}
          </section>}
          {!preview.valid && preview.problem_summary?.length > 0 && <div className="admin-csv-problem-summary"><strong>Problems found</strong><ul>{preview.problem_summary.map((item) => <li key={item.type}>{item.count} {item.message}</li>)}</ul></div>}
          {!preview.valid && invalidPreviewRows.length > 0 && <><button type="button" className="admin-csv-text-button" aria-expanded={showErrors} onClick={() => setShowErrors((current) => !current)}>{showErrors ? 'Hide details' : `Show details (${preview.invalid_rows})`}</button>
            {showErrors && <div className="admin-csv-error-rows">{invalidPreviewRows.slice(0, visibleErrorRows).map((row) => <article key={row.row_number}><strong>Row {row.row_number}</strong><span>{renderRowLabel(row)}</span><ul>{row.errors.map((item, index) => <li key={`${item.field}-${index}`}><b>{fieldLabels[item.field] || 'Problem'}:</b> {item.message}</li>)}</ul></article>)}
              {preview.invalid_rows > Math.min(visibleErrorRows, invalidPreviewRows.length) && <p>Showing {Math.min(visibleErrorRows, invalidPreviewRows.length)} of {preview.invalid_rows} problems.</p>}
              {invalidPreviewRows.length > visibleErrorRows && <button type="button" className="admin-csv-text-button" onClick={() => setVisibleErrorRows((count) => Math.min(100, count + 10))}>Show more</button>}
              {preview.errors_truncated && invalidPreviewRows.length >= 100 && <p>Showing the first 100 error details.</p>}
            </div>}
          </>}
          {active === 'assignments' && preview.valid && preview.skipped_existing > 0 && <p className="admin-csv-existing-note">Already-existing exact Teacher / Class / Subject assignments will be skipped safely.</p>}
        </section>}
        <div className="admin-csv-import-actions">
          {!preview && <button type="button" onClick={validateFile} disabled={!file || Boolean(busy)}>{busy === 'preview' ? 'Checking...' : 'Check File'}</button>}
          {preview?.valid && <button type="button" className="primary" onClick={importFile} disabled={!file || importCount === 0 || Boolean(busy)}>{busy === 'import' ? 'Importing...' : `Import ${importCount} ${active === 'assignments' ? 'New Assignments' : config.entity}`}</button>}
          {preview && !preview.valid && <button type="button" className="primary" disabled>Fix File First</button>}
        </div>
      </div>
    </section>
    <p className="admin-csv-footnote">Imports create new accounts and never update existing ones. Students enroll in existing classes only. Teachers receive hashed temporary passwords and must change them at first login; passwords are never included in preview or export.</p>
  </div>
}

export default AdminCsvManagement