import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './Home.css'
import { schoolProfile } from '../data/schoolProfile'

const navItems = [
  { label: 'Home', href: '#home' },
  { label: 'About Us', href: '#about' },
  { label: 'Academics', href: '#academics' },
  { label: 'Faculty', href: '#faculty' },
  { label: 'Notices', href: '#notices' },
  { label: 'Contact', href: '#contact' },
]

function Home() {
  const navigate = useNavigate()
  const [publicNotices, setPublicNotices] = useState([])

  useEffect(() => {
    api.get('/public/notices')
      .then((response) => setPublicNotices(response.data.notices || []))
      .catch(() => setPublicNotices([]))
  }, [])

  return (
    <div className="home-page">
      <div className="utility-bar">
        <div className="container utility-inner">
          <div className="utility-meta">
            <span>{schoolProfile.address}</span>
            <a href={`tel:${schoolProfile.phone.replace(/[^\d+]/g, '')}`}>{schoolProfile.phone}</a>
            <a href={`mailto:${schoolProfile.email}`}>{schoolProfile.email}</a>
          </div>

          <div className="utility-actions">
            <button type="button" className="utility-btn" onClick={() => navigate('/login')}>
              Student / Teacher Portal
            </button>
            <button type="button" className="utility-btn utility-btn-muted" onClick={() => navigate('/admin/login')}>
              Admin Portal
            </button>
          </div>
        </div>
      </div>

      <header className="site-header">
        <nav className="site-nav container" aria-label="Main navigation">
          <div className="brand" aria-label="Institution home">
            <div className="brand-mark" aria-hidden="true">
              <span>T</span>
            </div>
            <div className="brand-copy">
              <strong>{schoolProfile.name}</strong>
              <small>Academic Platform — Siksha Sarathi</small>
            </div>
          </div>

          <div className="nav-links">
            {navItems.map((item) => (
              <a key={item.href} href={item.href}>
                {item.label}
              </a>
            ))}
          </div>

          <div className="nav-actions">
            <button type="button" className="btn btn-primary" onClick={() => navigate('/login')}>
              Student / Teacher Portal
            </button>
            <button type="button" className="btn btn-link" onClick={() => navigate('/admin/login')}>
              Admin Portal
            </button>
          </div>
        </nav>
      </header>

      <main className="site-main">
        <section className="hero-section container" id="home">
          <div className="hero-copy">
            <p className="eyebrow">Welcome to</p>
            <h1>
              Empowering Minds.
              <span>Inspiring Futures.</span>
            </h1>
            <p className="hero-text">{schoolProfile.description}</p>

            <div className="hero-actions">
              <button type="button" className="btn btn-primary large" onClick={() => navigate('#academics')}>
                Explore Programs
              </button>
              <button type="button" className="btn btn-secondary large" onClick={() => navigate('/login')}>
                Student / Teacher Portal
              </button>
            </div>

            <div className="hero-meta-row">
              <span>Technology</span>
              <span>Management</span>
              <span>Student Development</span>
            </div>
          </div>

          <div className="hero-visual" aria-label="Academic overview illustration">
            <div className="visual-panel">
              <div className="visual-card large-card">
                <div className="mini-label">Academic Excellence</div>
                <h3>Technology • Management • Learning</h3>
              </div>

              <div className="visual-card floating-card top-card">
                <span>Student Support</span>
                <strong>Career Ready</strong>
              </div>

              <div className="visual-card floating-card bottom-card">
                <span>Powered by</span>
                <strong>Siksha Sarathi</strong>
              </div>

              <div className="grid-lines" aria-hidden="true" />
            </div>
          </div>
        </section>

        <section className="quick-access container" aria-label="Quick access links">
          <div className="quick-strip">
            {schoolProfile.quickAccess.map((item) => (
              <a className="quick-item" href={item.href} key={item.title}>
                <span className="quick-icon" aria-hidden="true">
                  {item.type === 'portal' ? '▣' : item.type === 'notice' ? '◌' : item.type === 'programs' ? '◍' : '◎'}
                </span>
                <div>
                  <strong>{item.title}</strong>
                  <small>{item.description}</small>
                </div>
                <span className="arrow" aria-hidden="true">→</span>
              </a>
            ))}
          </div>
        </section>

        <section className="content-section container" id="about">
          <div className="section-header">
            <p className="eyebrow">About Texas</p>
            <h2>Higher education for a changing world.</h2>
          </div>

          <div className="about-layout">
            <div className="about-copy">
              <p>{schoolProfile.about.whoWeAre}</p>
            </div>

            <div className="about-feature-grid">
              <article className="feature-block">
                <h3>Technology-Focused Learning</h3>
                <p>{schoolProfile.about.mission}</p>
              </article>
              <article className="feature-block">
                <h3>Management Education</h3>
                <p>{schoolProfile.about.vision}</p>
              </article>
              <article className="feature-block">
                <h3>Student Development</h3>
                <p>Our approach supports confidence, teamwork, and practical readiness for future academic and professional pathways.</p>
              </article>
            </div>
          </div>
        </section>

        <section className="content-section alt" id="academics">
          <div className="container">
            <div className="section-header narrow">
              <p className="eyebrow">Academic Offerings</p>
              <h2>Programs designed for the future.</h2>
            </div>

            <div className="program-grid">
              <article className="program-card featured">
                <span className="program-badge">Featured</span>
                <h3>BSc CSIT</h3>
                <p>Computing &amp; Information Technology</p>
              </article>

              <article className="program-card featured secondary">
                <span className="program-badge">Featured</span>
                <h3>BCA</h3>
                <p>Computer Applications</p>
              </article>

              {schoolProfile.academics
                .filter((program) => program.title !== 'BSc CSIT' && program.title !== 'BCA')
                .map((program) => (
                  <article className="program-card" key={program.title}>
                    <span className="program-badge">Program</span>
                    <h3>{program.title}</h3>
                    <p>{program.description}</p>
                  </article>
                ))}
            </div>
          </div>
        </section>

        <section className="content-section container" id="faculty">
          <div className="section-header narrow">
            <p className="eyebrow">Our Academic Community</p>
            <h2>Where learning, mentorship, and progress meet.</h2>
          </div>

          <div className="faculty-grid">
            {schoolProfile.faculty.map((person) => (
              <article className="faculty-card" key={person.role}>
                <div className="faculty-icon" aria-hidden="true">✦</div>
                <h3>{person.role}</h3>
                <p>{person.note}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section alt" id="notices">
          <div className="container">
            <div className="section-header narrow">
              <p className="eyebrow">Stay Updated</p>
              <h2>Notices &amp; Announcements</h2>
            </div>

            {publicNotices.length ? publicNotices.map((notice) => (
              <article className="notice-box" key={notice.id}>
                <div className="notice-icon" aria-hidden="true">📣</div>
                <div>
                  <div className="notice-date">{new Date(notice.created_at).toLocaleDateString()}</div>
                  <h3>{notice.title}</h3>
                  <p>{notice.body}</p>
                </div>
              </article>
            )) : <div className="notice-box">
              <div className="notice-icon" aria-hidden="true">📣</div>
              <div>
                <div className="notice-date">Public notice board</div>
                <h3>No public notices have been published.</h3>
                <p>Official institution-wide notices will appear here when available.</p>
              </div>
            </div>}
          </div>
        </section>

        <section className="portal-section" aria-label="Portal access">
          <div className="container portal-inner">
            <div className="portal-copy">
              <p className="eyebrow">Texas Student &amp; Staff Portal</p>
              <h2>Powered by Siksha Sarathi</h2>
              <p>
                Students and teachers can securely access learning resources, academic tools,
                assessments, support flows, and institutional workflows through the Siksha Sarathi platform.
              </p>
            </div>

            <div className="portal-actions">
              <button type="button" className="btn btn-primary" onClick={() => navigate('/login')}>
                Student / Teacher Portal
              </button>
              <button type="button" className="btn btn-secondary portal-secondary" onClick={() => navigate('/admin/login')}>
                Administration Portal
              </button>
            </div>
          </div>
        </section>

        <section className="content-section container" id="contact">
          <div className="section-header narrow">
            <p className="eyebrow">Get in Touch</p>
            <h2>Connect with Texas International College.</h2>
          </div>

          <div className="contact-panel">
            <div className="contact-identity">
              <h3>{schoolProfile.name}</h3>
              <p>{schoolProfile.address}</p>
            </div>

            <div className="contact-grid">
              <a href={`tel:${schoolProfile.phone.replace(/[^\d+]/g, '')}`}>
                <span>Phone</span>
                <strong>{schoolProfile.phone}</strong>
              </a>
              <a href={`mailto:${schoolProfile.email}`}>
                <span>Email</span>
                <strong>{schoolProfile.email}</strong>
              </a>
              <div>
                <span>Location</span>
                <strong>{schoolProfile.address}</strong>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container footer-inner">
          <div className="footer-brand-block">
            <h3>{schoolProfile.name}</h3>
            <p>
              A modern learning environment focused on academic excellence, technology,
              management, and student development.
            </p>
          </div>

          <div className="footer-links">
            <h4>Explore</h4>
            <a href="#about">About</a>
            <a href="#academics">Academics</a>
            <a href="#faculty">Faculty</a>
            <a href="#notices">Notices</a>
          </div>

          <div className="footer-links">
            <h4>Portals</h4>
            <a href="/login">Student / Teacher Portal</a>
            <a href="/admin/login">Admin Portal</a>
          </div>

          <div className="footer-links">
            <h4>Contact</h4>
            <span>{schoolProfile.address}</span>
            <a href={`tel:${schoolProfile.phone.replace(/[^\d+]/g, '')}`}>{schoolProfile.phone}</a>
            <a href={`mailto:${schoolProfile.email}`}>{schoolProfile.email}</a>
          </div>
        </div>

        <div className="bottom-bar">
          <div className="container bottom-bar-inner">
            <span>© 2026 Texas International College</span>
            <span>Academic Platform powered by Siksha Sarathi</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Home
