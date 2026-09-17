import {useQuery} from '@tanstack/react-query'

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

export type LocalMediaProfileTemplateSourcesResponse = {
    sources: LocalMediaProfileTemplateSource[]
    variables?: LocalMediaProfileTemplateVariable[]
}

export function useLocalMediaProfileTemplateSources(
    mode: LocalMediaProfileTemplateSourceMode,
    showScope: ShowLocalMediaProfileScope = 'both',
    enabled = true,
) {
    return useQuery<LocalMediaProfileTemplateSourcesResponse>({
        queryKey: ['localMediaProfileTemplateSources', mode, showScope],
        enabled,
        queryFn: async ({signal}) => {
            const params = new URLSearchParams({type: mode})
            if (mode === 'show') params.set('show_scope', showScope)
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/local-media-profiles/template/sources?${params.toString()}`,
                {signal, credentials: 'include'},
            )
            if (!response.ok) throw new Error(`Failed to load template examples (${response.status})`)
            return response.json()
        },
        staleTime: 30_000,
    })
}
