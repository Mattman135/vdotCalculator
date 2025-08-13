import axios from "axios"

// Prefer Vite env var if provided, otherwise default to local backend
const baseURL = import.meta.env?.VITE_API_URL || "http://localhost:8000"

const api = axios.create({ baseURL })

export default api
