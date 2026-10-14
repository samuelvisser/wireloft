import { QueryClient } from '@tanstack/react-query'

// Central QueryClient with sensible defaults for caching
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 7 * 24 * 60 * 60 * 1000, // 7 days for inactive queries
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})
