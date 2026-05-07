import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Don't retry 4xx errors
        if (
          error instanceof Error &&
          'status' in error &&
          typeof (error as { status: number }).status === 'number' &&
          (error as { status: number }).status < 500
        ) {
          return false
        }
        return failureCount < 2
      },
      staleTime: 30_000,
    },
  },
})

const root = document.getElementById('root')
if (!root) throw new Error('Root element #root not found in index.html')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </StrictMode>,
)
