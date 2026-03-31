import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Books } from './pages/Books'
import { BookDetail } from './pages/BookDetail'
import { Orders } from './pages/Orders'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { ProtectedRoute } from './components/ProtectedRoute'
import { getToken } from './api'

function RedirectRoot() {
  const token = getToken()
  return <Navigate to={token ? '/books' : '/login'} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RedirectRoot />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/books" element={<ProtectedRoute><Books /></ProtectedRoute>} />
        <Route path="/books/:id" element={<ProtectedRoute><BookDetail /></ProtectedRoute>} />
        <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}

// Verification steps:
// /login with valid credentials          → redirect to /books
// /login with invalid credentials        → error message shown
// /books without token                   → redirect to /login
// /books/:id → Place Order               → POST /orders, success message
// /orders                                → list of user orders
// Logout                                 → clears token, redirects to /login
// Page refresh on /books                 → stays on /books (nginx try_files)
