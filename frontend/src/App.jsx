import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import api from './api'

import Home from './pages/Home'
import Login from './pages/Login'
import StudentRegister from './pages/StudentRegister'
import TeacherRegister from './pages/TeacherRegister'

import StudentLayout from './components/StudentLayout'
import TeacherLayout from './components/TeacherLayout'
import StudentDashboard from './pages/StudentDashboard'
import Quiz from './pages/Quiz'
import Notes from './pages/Notes'
import Performance from './pages/Performance'
import AIAssistant from './pages/AIAssistant'
import TeacherDashboard from './pages/TeacherDashboard'
import TeacherNotes from './pages/TeacherNotes'
import AdminDashboard from './pages/AdminDashboard'
import TeacherUploadNote from './pages/TeacherUploadNote'

// ---------- Auth Context Helper ----------
function useAuthCheck() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Only check auth if we are not on public pages
    const publicPaths = ['/', '/login', '/student/register', '/teacher/register']
    if (publicPaths.includes(window.location.pathname)) {
      setLoading(false)
      return
    }

    api
      .get('/auth/me')
      .then((res) => {
        setUser(res.data.user)
      })
      .catch(() => {
        setUser(null)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  return { user, loading }
}

// ---------- Protected Route ----------
function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading } = useAuthCheck()

  if (loading) {
    return (
      <div style={{ padding: '60px', textAlign: 'center' }}>
        Checking authentication...
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    // Redirect to correct dashboard
    if (user.role === 'student') return <Navigate to="/student/dashboard" replace />
    if (user.role === 'teacher') return <Navigate to="/teacher/dashboard" replace />
    if (user.role === 'admin') return <Navigate to="/admin/dashboard" replace />
    return <Navigate to="/login" replace />
  }

  return children
}

function StudentPage({ children }) {
  return (
    <ProtectedRoute allowedRoles={['student']}>
      <StudentLayout>{children}</StudentLayout>
    </ProtectedRoute>
  )
}

function TeacherPage({ children }) {
  return (
    <ProtectedRoute allowedRoles={['teacher']}>
      <TeacherLayout>{children}</TeacherLayout>
    </ProtectedRoute>
  )
}

function AdminPage({ children }) {
  return (
    <ProtectedRoute allowedRoles={['admin']}>
      {children}
    </ProtectedRoute>
  )
}

// ---------- App ----------
function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/student/register" element={<StudentRegister />} />
        <Route path="/teacher/register" element={<TeacherRegister />} />

        {/* Student routes */}
        <Route path="/student/dashboard" element={
          <StudentPage><StudentDashboard /></StudentPage>
        } />
        <Route path="/student/quiz" element={
          <StudentPage><Quiz /></StudentPage>
        } />
        <Route path="/student/notes" element={
          <StudentPage><Notes /></StudentPage>
        } />
        <Route path="/student/performance" element={
          <StudentPage><Performance /></StudentPage>
        } />
        <Route path="/student/ai" element={
          <StudentPage><AIAssistant /></StudentPage>
        } />

        {/* Teacher routes */}
        <Route path="/teacher/dashboard" element={
          <TeacherPage><TeacherDashboard /></TeacherPage>
        } />
        <Route path="/teacher/notes" element={
          <TeacherPage><TeacherNotes /></TeacherPage>
        } />

        <Route path="/teacher/upload" element={
          <TeacherPage><TeacherUploadNote /></TeacherPage>
        } />

        {/* Admin */}
        <Route path="/admin/dashboard" element={
          <AdminPage><AdminDashboard /></AdminPage>
        } />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App