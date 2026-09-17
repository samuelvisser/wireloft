import {useQuery} from '@tanstack/react-query'

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
    enabled = true,
) {
    return useQuery<LocalMediaProfileTemplateSourcesResponse>({
        queryKey: ['localMediaProfileTemplateSources', mode],
        enabled,
        queryFn: async ({signal}) => {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/local-media-profiles/template/sources?type=${mode}`,
                {signal, credentials: 'include'},
            )
            if (!response.ok) throw new Error(`Failed to load template examples (${response.status})`)
            return response.json()
        },
        staleTime: 30_000,
    })
}
