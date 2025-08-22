import { QueryClient } from '@tanstack/react-query'

// Central QueryClient with sensible defaults for caching
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 30 * 60 * 1000, // 30 minutes (v5 option)
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})
