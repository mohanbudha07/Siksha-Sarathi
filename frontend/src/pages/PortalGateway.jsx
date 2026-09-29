import { useNavigate } from 'react-router-dom'
import { schoolProfile } from '../data/schoolProfile'
import './PortalGateway.css'

function PortalGateway() {
  const navigate = useNavigate()

  return (
    <main className="portal-gateway-page">
      <header className="portal-gateway-header">
        <a href="/" className="portal-gateway-brand">{schoolProfile.name}</a>
        <a href="/" className="portal-gateway-home">Institution website</a>
      </header>
      <section className="portal-gateway-content">
        <p className="portal-gateway-eyebrow">SIKSHA SARATHI</p>
        <h1>Siksha Sarathi Portal</h1>
        <p className="portal-gateway-intro">Choose how you access your school workspace.</p>
        <div className="portal-gateway-options">
          <article className="portal-gateway-option portal-gateway-primary">
            <div>
              <p className="portal-gateway-option-label">LEARNING WORKSPACE</p>
              <h2>Student &amp; Teacher</h2>
              <p>Use your school-issued account.</p>
            </div>
            <button type="button" onClick={() => navigate('/login')}>Continue <span aria-hidden="true">→</span></button>
          </article>
          <article className="portal-gateway-option portal-gateway-admin">
            <div>
              <p className="portal-gateway-option-label">SCHOOL ADMINISTRATION</p>
              <h2>Administration</h2>
              <p>Authorized school administrators only.</p>
            </div>
            <button type="button" onClick={() => navigate('/admin/login')}>Administration Sign In <span aria-hidden="true">→</span></button>
          </article>
        </div>
      </section>
    </main>
  )
}

export default PortalGateway