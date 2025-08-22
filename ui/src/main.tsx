import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'
import { queryClient } from './lib/queryClient'
import { prefetchCoreData } from './lib/queries'

// Warm the cache on startup to avoid loading flashes
prefetchCoreData(queryClient)

const rootEl = document.getElementById('root') as HTMLElement
createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
