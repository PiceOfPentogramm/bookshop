import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, decodeToken } from '../api'
import { Navbar } from '../components/Navbar'

export function BookDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [book, setBook] = useState(null)
  const [quantity, setQuantity] = useState(1)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.getBook(id).then(setBook).catch((err) => setError(err.message))
  }, [id])

  const handleOrder = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    const payload = decodeToken()
    if (!payload?.sub) {
      navigate('/login')
      return
    }
    setLoading(true)
    try {
      await api.createOrder({ bookId: id, quantity: Number(quantity), userId: payload.sub })
      setSuccess('Order placed successfully')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!book) {
    return (
      <>
        <Navbar />
        <div className="container">{error || 'Loading...'}</div>
      </>
    )
  }

  return (
    <>
      <Navbar />
      <div className="container" style={{ maxWidth: 720 }}>
        <div className="card">
          <h2>{book.title}</h2>
          <p style={{ color: '#cbd5e1' }}>{book.author}</p>
          <p style={{ color: '#cbd5e1' }}>Genre: {book.genre || '—'}</p>
          <p style={{ marginBottom: 16 }}>${book.price.toFixed(2)} • Stock: {book.stock}</p>
          <form onSubmit={handleOrder}>
            <label style={{ display: 'block', marginBottom: 8 }}>Quantity</label>
            <input className="input" type="number" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            <button className="btn" type="submit" disabled={loading}>{loading ? 'Placing...' : 'Place Order'}</button>
          </form>
          {error && <div className="error">{error}</div>}
          {success && <div className="success">{success}</div>}
        </div>
      </div>
    </>
  )
}
