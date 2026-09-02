import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {
    SettingsFieldPath,
    SettingsRead,
    SettingsReadSchema,
    SettingsUpdateSchema,
    SettingsValues,
} from '../types/schemas/settings'


function settingsUrl() {
    const base = (window as any).appConfig?.API_URL?.replace(/\/+$/, '')
    return `${base}/settings`
}

async function errorFromResponse(response: Response, fallback: string): Promise<Error> {
    try {
        const payload = await response.json()
        if (typeof payload?.detail === 'string') return new Error(payload.detail)
    } catch {
        // Use the fallback below when the response has no JSON error body.
    }
    return new Error(`${fallback} (HTTP ${response.status})`)
}

async function readSettings(response: Response, fallback: string): Promise<SettingsRead> {
    if (!response.ok) throw await errorFromResponse(response, fallback)
    return SettingsReadSchema.parse(await response.json())
}

export async function saveSettingsRequest({
    values,
    changedFields,
}: {
    values: SettingsValues
    changedFields: SettingsFieldPath[]
}): Promise<Response> {
    const body = SettingsUpdateSchema.parse({values, changedFields})
    return fetch(settingsUrl(), {
        method: 'PUT',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
    })
}

export function useSettings() {
    return useQuery({
        queryKey: ['settings'] as const,
        queryFn: async ({signal}) => {
            const response = await fetch(settingsUrl(), {
                signal,
                credentials: 'include',
            })
            return readSettings(response, 'Failed to load settings')
        },
        refetchOnMount: 'always',
    })
}

export function useSaveSettings() {
    const queryClient = useQueryClient()
    return useMutation({
        mutationFn: async ({
            values,
            changedFields,
        }: {
            values: SettingsValues
            changedFields: SettingsFieldPath[]
        }) => {
            const response = await saveSettingsRequest({values, changedFields})
            return readSettings(response, 'Failed to save settings')
        },
        onSuccess: (settings) => {
            queryClient.setQueryData(['settings'], settings)
        },
    })
}
