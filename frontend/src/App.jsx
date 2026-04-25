import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'

import Layout from './components/Layout.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'

import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import EmergencyForm from './pages/EmergencyForm.jsx'
import AmbulanceTracking from './pages/AmbulanceTracking.jsx'
import HospitalAvailability from './pages/HospitalAvailability.jsx'
import Analytics from './pages/Analytics.jsx'

import { connectSocket, disconnectSocket } from './api/socket.js'
import { useAuthStore } from './store/auth.js'

export default function App() {
  const token = useAuthStore(s => s.token)

  // Connect socket once we have a token; reconnect when token changes.
  useEffect(() => {
    if (token) connectSocket()
    return () => disconnectSocket()
  }, [token])

  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/"           element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard"  element={<Dashboard />} />
        <Route path="/intake"     element={<EmergencyForm />} />
        <Route path="/ambulances" element={<AmbulanceTracking />} />
        <Route path="/hospitals"  element={<HospitalAvailability />} />
        <Route path="/analytics"  element={<Analytics />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
