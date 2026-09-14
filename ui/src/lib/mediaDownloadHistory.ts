import {useInfiniteQuery} from '@tanstack/react-query'
import {MediaDownloadHistoryPageReadSchema} from '../types/schemas/media_download_history'

export function useMediaDownloadHistory(mediaDownloadId?: number, limit = 50) {
    return useInfiniteQuery({
        queryKey: ['mediaDownloadHistory', mediaDownloadId, limit] as const,
        enabled: mediaDownloadId != null,
        initialPageParam: 0,
        queryFn: async ({pageParam, signal}) => {
            const params = new URLSearchParams({
                offset: String(pageParam),
                limit: String(limit),
            })
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/media-downloads/${mediaDownloadId}/history?${params}`,
                {signal, credentials: 'include'},
            )
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            return MediaDownloadHistoryPageReadSchema.parse(await response.json())
        },
        getNextPageParam: (lastPage) => lastPage.hasMore
            ? lastPage.offset + lastPage.items.length
            : undefined,
        refetchOnMount: 'always',
    })
}
