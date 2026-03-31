const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const getToken = () => localStorage.getItem('token');
export const setToken = (token) => localStorage.setItem('token', token);
export const clearToken = () => localStorage.removeItem('token');

export const decodeToken = () => {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload;
  } catch (e) {
    return null;
  }
};

const handleUnauthorized = () => {
  clearToken();
  window.location.href = '/login';
};

const request = async (path, options = {}) => {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  try {
    const resp = await fetch(`${API_URL}${path}`, { ...options, headers });
    if (resp.status === 401) {
      handleUnauthorized();
      throw new Error('Unauthorized');
    }
    const text = await resp.text();
    const data = text ? JSON.parse(text) : null;
    if (!resp.ok) {
      const msg = data?.detail || 'Request failed';
      throw new Error(msg);
    }
    return data;
  } catch (err) {
    if (err.name === 'SyntaxError') {
      throw new Error('Invalid response from server');
    }
    throw err;
  }
};

export const api = {
  login: (email, password) => request('/users/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (email, password) => request('/users/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
  getBooks: () => request('/books', { method: 'GET' }),
  getBook: (id) => request(`/books/${id}`, { method: 'GET' }),
  createOrder: ({ bookId, quantity, userId }) => request('/orders', { method: 'POST', body: JSON.stringify({ book_id: bookId, user_id: userId, quantity }) }),
  getOrders: (userId) => request(`/orders/user/${userId}`, { method: 'GET' }),
};
