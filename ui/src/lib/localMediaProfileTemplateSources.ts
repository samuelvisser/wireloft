import {useState} from 'react'
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
    anchorSourceId?: string
}

async function fetchTemplateJson<T>(
    path: string,
    signal?: AbortSignal,
    cache?: RequestCache,
): Promise<T> {
    const response = await fetch(
        `${(window as any).appConfig.API_URL}/local-media-profiles/template/${path}`,
        {signal, credentials: 'include', cache},
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
        anchorSourceId,
    }: LocalMediaProfileTemplateSourceOptions = {},
) {
    const effectiveAnchorSourceId = mode === 'show' && !search.trim()
        ? anchorSourceId
        : undefined
    return useInfiniteQuery<LocalMediaProfileTemplateSourcePage>({
        queryKey: [
            'localMediaProfileTemplateSources',
            mode,
            showScope,
            search,
            pageSize,
            effectiveAnchorSourceId,
        ],
        enabled,
        initialPageParam: effectiveAnchorSourceId ? 'anchor' : 0,
        queryFn: async ({pageParam, signal}) => {
            const params = new URLSearchParams({
                type: mode,
                limit: String(pageSize),
            })
            if (pageParam === 'anchor' && effectiveAnchorSourceId) {
                params.set('anchor_source_id', effectiveAnchorSourceId)
            } else {
                params.set('offset', String(pageParam))
            }
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
        getPreviousPageParam: (firstPage) => firstPage.offset > 0
            ? Math.max(0, firstPage.offset - firstPage.limit)
            : undefined,
        staleTime: 30_000,
    })
}


export function useRandomShowTemplateSource(
    showScope: ShowLocalMediaProfileScope = 'both',
    enabled = true,
) {
    // A per-mount key makes reopening the form request a fresh example instead
    // of reusing React Query's cache from the previous page visit.
    const [requestKey] = useState(() => Math.random())
    return useQuery<LocalMediaProfileTemplateSource | null>({
        queryKey: ['randomShowTemplateSource', showScope, requestKey],
        enabled,
        queryFn: ({signal}) => fetchTemplateJson(
            `sources/random-show-episode?show_scope=${encodeURIComponent(showScope)}`,
            signal,
            'no-store',
        ),
        staleTime: Infinity,
    })
}
