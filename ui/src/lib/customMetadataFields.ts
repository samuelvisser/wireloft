import {useQuery} from '@tanstack/react-query'

export type CustomMetadataFieldScope = 'show' | 'movie'

export function useCustomMetadataFields(
    scope: CustomMetadataFieldScope,
    enabled = true,
) {
    return useQuery<string[]>({
        queryKey: ['customMetadataFields', scope],
        enabled,
        queryFn: async ({signal}) => {
            const params = new URLSearchParams({scope})
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/custom-metadata/fields?${params.toString()}`,
                {signal, credentials: 'include'},
            )
            if (!response.ok) throw new Error(`Failed to load custom metadata fields (${response.status})`)
            return response.json()
        },
        staleTime: 30_000,
    })
}
