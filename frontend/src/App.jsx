import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import StudentLayout from './components/StudentLayout'
import StudentDashboard from './pages/StudentDashboard'
import Quiz from './pages/Quiz'
import Notes from './pages/Notes'
import Performance from './pages/Performance'
import AIAssistant from './pages/AIAssistant'

function StudentPage({ children }) {
  return (
    <StudentLayout>
      {children}
    </StudentLayout>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>

        <Route
          path="/"
          element={<Navigate to="/login" replace />}
        />

        <Route
          path="/login"
          element={<Login />}
        />

        <Route
          path="/student/dashboard"
          element={
            <StudentPage>
              <StudentDashboard />
            </StudentPage>
          }
        />

        <Route
          path="/student/quiz"
          element={
            <StudentPage>
              <Quiz />
            </StudentPage>
          }
        />

        <Route
          path="/student/notes"
          element={
            <StudentPage>
              <Notes />
            </StudentPage>
          }
        />

        <Route
          path="/student/performance"
          element={
            <StudentPage>
              <Performance />
            </StudentPage>
          }
        />

        <Route
          path="/student/ai"
          element={
            <StudentPage>
              <AIAssistant />
            </StudentPage>
          }
        />

        <Route
          path="*"
          element={<Navigate to="/login" replace />}
        />

      </Routes>
    </BrowserRouter>
  )
}

export default App
