import { Link, useNavigate } from 'react-router-dom'
import { clearToken, decodeToken } from '../api'

export function Navbar() {
  const navigate = useNavigate()
  const payload = decodeToken()
  const email = payload?.email || 'Account'

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <nav>
      <div className="nav-content">
        <div style={{ fontWeight: 700 }}>Bookshop</div>
        <div className="links">
          <Link to="/books">Books</Link>
          <Link to="/orders">My Orders</Link>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: '#cbd5e1', fontSize: 14 }}>{email}</span>
          <button className="btn" onClick={handleLogout}>Logout</button>
        </div>
      </div>
    </nav>
  )
}
