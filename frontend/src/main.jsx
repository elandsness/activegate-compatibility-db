/* React 18 SSR-ready entry point for Vite. */

import { createRoot } from 'react-dom/client'
import App           from './App'
import './styles.css'

createRoot(document.getElementById('root')).render(<App />)
