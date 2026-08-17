import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import StudentDashboard from './pages/StudentDashboard'
import Quiz from './pages/Quiz'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/student/dashboard" element={<StudentDashboard />} />
        <Route path="/student/quiz" element={<Quiz />} />
        <Route path="*" element={<Navigate to="/student/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
