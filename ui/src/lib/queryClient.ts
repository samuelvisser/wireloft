import { QueryClient, timeoutManager } from '@tanstack/react-query'
import {createLongTimeoutProvider} from './longTimeoutProvider'

// Configure long timers before creating any queries. Native setTimeout overflows after ~24 days.
timeoutManager.setTimeoutProvider(createLongTimeoutProvider())

// Central QueryClient with sensible defaults for caching
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 30 * 24 * 60 * 60 * 1000, // 30 days for inactive queries
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})
