import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Navbar } from '../components/Navbar'

export function Books() {
  const [books, setBooks] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.getBooks().then(setBooks).catch((err) => setError(err.message))
  }, [])

  return (
    <>
      <Navbar />
      <div className="container">
        <h2>Books</h2>
        {error && <div className="error">{error}</div>}
        <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {books.map((book) => (
            <div key={book.id} className="card">
              <h3 style={{ margin: '0 0 8px' }}>{book.title}</h3>
              <p style={{ color: '#cbd5e1', margin: '0 0 4px' }}>{book.author}</p>
              <p style={{ color: '#cbd5e1', margin: '0 0 4px' }}>Genre: {book.genre || '—'}</p>
              <p style={{ margin: '0 0 8px' }}>${book.price.toFixed(2)} • Stock: {book.stock}</p>
              <Link className="btn" to={`/books/${book.id}`}>View</Link>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
