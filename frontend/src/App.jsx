import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import StudentDashboard from './pages/StudentDashboard'
import Quiz from './pages/Quiz'
import Notes from './pages/Notes'
import Performance from './pages/Performance'
import AIAssistant from './pages/AIAssistant'

function App() {
  return (
    <BrowserRouter>
      <Routes>

        <Route
          path="/student/dashboard"
          element={<StudentDashboard />}
        />

        <Route
          path="/student/quiz"
          element={<Quiz />}
        />

        <Route
          path="/student/notes"
          element={<Notes />}
        />

        <Route
          path="/student/performance"
          element={<Performance />}
        />

        <Route
          path="/student/ai"
          element={<AIAssistant />}
        />

        <Route
          path="*"
          element={
            <Navigate
              to="/student/dashboard"
              replace
            />
          }
        />

      </Routes>
    </BrowserRouter>
  )
}

export default App
