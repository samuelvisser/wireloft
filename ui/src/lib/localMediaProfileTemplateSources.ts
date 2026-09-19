import {useInfiniteQuery, useQuery} from '@tanstack/react-query'

import type {ShowLocalMediaProfileScope} from '../types/local_media_profile'

export type LocalMediaProfileTemplateSourceMode = 'show' | 'movie'

export type LocalMediaProfileTemplateVariable = {
    name: string
    description: string
}

export type LocalMediaProfileTemplateSource = {
    id: string
    label: string
    values: Record<string, string>
    fallback: boolean
}

export type LocalMediaProfileTemplateSourcePage = {
    items: LocalMediaProfileTemplateSource[]
    offset: number
    limit: number
    hasMore: boolean
}

type LocalMediaProfileTemplateSourceOptions = {
    showScope?: ShowLocalMediaProfileScope
    search?: string
    enabled?: boolean
    pageSize?: number
}

async function fetchTemplateJson<T>(path: string, signal?: AbortSignal): Promise<T> {
    const response = await fetch(
        `${(window as any).appConfig.API_URL}/local-media-profiles/template/${path}`,
        {signal, credentials: 'include'},
    )
    if (!response.ok) throw new Error(`Failed to load template data (${response.status})`)
    return response.json() as Promise<T>
}

export function useLocalMediaProfileTemplateVariables(
    mode: LocalMediaProfileTemplateSourceMode,
    enabled = true,
) {
    return useQuery<LocalMediaProfileTemplateVariable[]>({
        queryKey: ['localMediaProfileTemplateVariables', mode],
        enabled,
        queryFn: ({signal}) => fetchTemplateJson(
            `variables?type=${encodeURIComponent(mode)}`,
            signal,
        ),
        staleTime: 30_000,
    })
}

export function useLocalMediaProfileTemplateSources(
    mode: LocalMediaProfileTemplateSourceMode,
    {
        showScope = 'both',
        search = '',
        enabled = true,
        pageSize = 30,
    }: LocalMediaProfileTemplateSourceOptions = {},
) {
    return useInfiniteQuery<LocalMediaProfileTemplateSourcePage>({
        queryKey: ['localMediaProfileTemplateSources', mode, showScope, search, pageSize],
        enabled,
        initialPageParam: 0,
        queryFn: async ({pageParam, signal}) => {
            const params = new URLSearchParams({
                type: mode,
                offset: String(pageParam),
                limit: String(pageSize),
            })
            if (mode === 'show') params.set('show_scope', showScope)
            if (search.trim()) params.set('search', search.trim())
            return fetchTemplateJson<LocalMediaProfileTemplateSourcePage>(
                `sources?${params.toString()}`,
                signal,
            )
        },
        getNextPageParam: (lastPage) => lastPage.hasMore
            ? lastPage.offset + lastPage.items.length
            : undefined,
        staleTime: 30_000,
    })
}
