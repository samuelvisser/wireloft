import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'

import {useLazyCollection} from './lazyCollection'

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
    limit: number
    nextCursor?: string | null
    previousCursor?: string | null
    hasMore: boolean
    hasPrevious?: boolean
    revision: string
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

    return useLazyCollection<LocalMediaProfileTemplateSource>({
        collectionPrefix: ['localMediaProfileTemplateSources'] as const,
        queryKey: [
            mode,
            showScope,
            search.trim(),
            effectiveAnchorSourceId ?? null,
        ] as const,
        initialCount: pageSize,
        batchSize: pageSize,
        enabled,
        fetchPage: async ({cursor, limit}, signal) => {
            const params = new URLSearchParams({
                type: mode,
                limit: String(limit),
            })
            if (cursor) {
                params.set('cursor', cursor)
            } else if (effectiveAnchorSourceId) {
                params.set('anchor_source_id', effectiveAnchorSourceId)
            }
            if (mode === 'show') params.set('show_scope', showScope)
            if (search.trim()) params.set('search', search.trim())
            return fetchTemplateJson<LocalMediaProfileTemplateSourcePage>(
                `sources?${params.toString()}`,
                signal,
            )
        },
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
