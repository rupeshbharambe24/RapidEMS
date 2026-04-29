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
import PatientDashboard from './pages/PatientDashboard.jsx'
import AmbulanceDriverDashboard from './pages/AmbulanceDriverDashboard.jsx'
import HospitalPortal from './pages/HospitalPortal.jsx'
import Admin from './pages/Admin.jsx'
import FamilyTracking from './pages/FamilyTracking.jsx'

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

      {/* Public next-of-kin tracking — no auth, token-only */}
      <Route path="/track/:token" element={<FamilyTracking />} />

      {/* Patient surface — own chrome, no dispatcher sidebar */}
      <Route path="/patient" element={
        <ProtectedRoute><PatientDashboard /></ProtectedRoute>
      }/>

      {/* Paramedic / driver surface — full-screen map, no dispatcher sidebar */}
      <Route path="/driver" element={
        <ProtectedRoute><AmbulanceDriverDashboard /></ProtectedRoute>
      }/>

      {/* Hospital staff surface — alert feed + bed editor */}
      <Route path="/hospital" element={
        <ProtectedRoute><HospitalPortal /></ProtectedRoute>
      }/>

      {/* Dispatcher / clinical / admin surface */}
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/"           element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard"  element={<Dashboard />} />
        <Route path="/intake"     element={<EmergencyForm />} />
        <Route path="/ambulances" element={<AmbulanceTracking />} />
        <Route path="/hospitals"  element={<HospitalAvailability />} />
        <Route path="/analytics"  element={<Analytics />} />
        <Route path="/admin"      element={<Admin />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
