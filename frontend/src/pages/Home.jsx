import { useNavigate } from 'react-router-dom'
import './Home.css'

function Home() {
  const navigate = useNavigate()

  return (
    <div className="home-page">

      <nav className="home-navbar">
        <div className="home-logo">
          <span className="home-logo-icon">🎓</span>
          <span>Siksha Sarathi</span>
        </div>

        <button
          className="home-login-button"
          onClick={() => navigate('/login')}
        >
          Sign In
        </button>
      </nav>

      <main className="home-content">

        <section className="home-hero">

          <div className="home-badge">
            ✨ Smart Learning Platform
          </div>

          <h1>
            Learn Smarter.
            <br />
            <span>Grow Better.</span>
          </h1>

          <p>
            Siksha Sarathi is a smart e-learning platform designed
            to help students learn effectively and help teachers
            manage learning more efficiently.
          </p>

        </section>

        <section className="role-section">

          <h2>How would you like to continue?</h2>

          <p className="role-subtitle">
            Choose your role to create an account
          </p>

          <div className="role-cards">

            <div className="role-card student-card">

              <div className="role-icon">
                👨‍🎓
              </div>

              <h3>I'm a Student</h3>

              <p>
                Learn lessons, practice quizzes, read notes,
                track your performance and improve your skills.
              </p>

              <button
                onClick={() => navigate('/student/register')}
              >
                Register as Student →
              </button>

              <span
                className="role-login"
                onClick={() => navigate('/login')}
              >
                Already a student? Sign in
              </span>

            </div>

            <div className="role-card teacher-card">

              <div className="role-icon">
                👨‍🏫
              </div>

              <h3>I'm a Teacher</h3>

              <p>
                Manage learning resources, upload notes and
                support students through a smart teaching platform.
              </p>

              <button
                onClick={() => navigate('/teacher/register')}
              >
                Register as Teacher →
              </button>

              <span
                className="role-login"
                onClick={() => navigate('/login')}
              >
                Already a teacher? Sign in
              </span>

            </div>

          </div>

        </section>

        <section className="home-features">

          <div>
            <span>📚</span>
            <strong>Learning Notes</strong>
            <p>Access organized study materials.</p>
          </div>

          <div>
            <span>📝</span>
            <strong>Smart Quizzes</strong>
            <p>Practice and test your knowledge.</p>
          </div>

          <div>
            <span>📊</span>
            <strong>Performance Tracking</strong>
            <p>Understand your learning progress.</p>
          </div>

          <div>
            <span>🤖</span>
            <strong>AI Learning Assistant</strong>
            <p>Get help whenever you need it.</p>
          </div>

        </section>

      </main>

      <footer className="home-footer">
        © 2026 Siksha Sarathi · Smart Learning for Better Education
      </footer>

    </div>
  )
}

export default Home

