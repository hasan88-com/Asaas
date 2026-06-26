import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles/globals.css'

// Hide screen loader when React mounts
const loader = document.getElementById('screen-loader')
if (loader) {
  loader.classList.add('fade-out')
  setTimeout(() => loader.remove(), 300)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
