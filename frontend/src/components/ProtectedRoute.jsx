import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/auth.js'

export default function ProtectedRoute({ children }) {
  const token = useAuthStore(s => s.token)
  const loc = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  return children
}
