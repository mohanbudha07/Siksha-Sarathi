import AdminDashboard from './pages/AdminDashboard'
import TeacherNotes from './pages/TeacherNotes'
import StudentRegister from './pages/StudentRegister'
import Home from './pages/Home'
import TeacherRegister from './pages/TeacherRegister'
import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

import api from './api'

import Login from './pages/Login'
import StudentLayout from './components/StudentLayout'
import StudentDashboard from './pages/StudentDashboard'
import Quiz from './pages/Quiz'
import Notes from './pages/Notes'
import Performance from './pages/Performance'
import AIAssistant from './pages/AIAssistant'
import TeacherLayout from './components/TeacherLayout'
import TeacherDashboard from './pages/TeacherDashboard'

function ProtectedRoute({ children }) {
  const [checking, setChecking] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    api
      .get('/student/dashboard')
      .then((response) => {
        if (response.data?.student) {
          setAuthenticated(true)
        } else {
          setAuthenticated(false)
        }
      })
      .catch((error) => {
        console.error('Authentication check failed:', error)
        setAuthenticated(false)
      })
      .finally(() => {
        setChecking(false)
      })
  }, [])

  if (checking) {
    return <p>Checking authentication...</p>
  }

  if (!authenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}


function StudentPage({ children }) {
  return (
    <ProtectedRoute>
      <StudentLayout>
        {children}
      </StudentLayout>
    </ProtectedRoute>
  )
}
function TeacherPage({ children }) {
  return (
    <TeacherLayout>
      {children}
    </TeacherLayout>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>

        <Route
  path="/"
  element={<Home />}
/>

        <Route
          path="/login"
          element={<Login />}
        />
<Route
  path="/student/register"
  element={<StudentRegister />}
/>

<Route
  path="/teacher/register"
  element={<TeacherRegister />}
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
  path="/teacher/dashboard"
  element={
    <TeacherPage>
      <TeacherDashboard />
    </TeacherPage>
  }
/>

<Route
  path="/teacher/notes"
  element={
    <TeacherPage>
      <TeacherNotes />
    </TeacherPage>
  }
/>

<Route
  path="/admin/dashboard"
  element={<AdminDashboard />}
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
