import { useEffect, useState } from 'react'
import { api, decodeToken } from '../api'
import { Navbar } from '../components/Navbar'

export function Orders() {
  const [orders, setOrders] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    const payload = decodeToken()
    if (!payload?.sub) {
      setError('Not authenticated')
      return
    }
    api.getOrders(payload.sub).then(setOrders).catch((err) => setError(err.message))
  }, [])

  return (
    <>
      <Navbar />
      <div className="container">
        <h2>My Orders</h2>
        {error && <div className="error">{error}</div>}
        <div style={{ display: 'grid', gap: 12 }}>
          {orders.map((order) => (
            <div key={order.id} className="card">
              <p style={{ margin: 0 }}>Book ID: {order.book_id}</p>
              <p style={{ margin: '4px 0' }}>Quantity: {order.quantity}</p>
              <p style={{ margin: '4px 0' }}>Total: ${order.total_price.toFixed(2)}</p>
              <p style={{ margin: 0 }}>Status: {order.status}</p>
            </div>
          ))}
          {orders.length === 0 && !error && <p style={{ color: '#cbd5e1' }}>No orders yet.</p>}
        </div>
      </div>
    </>
  )
}
