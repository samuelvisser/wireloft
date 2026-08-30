import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {
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
        mutationFn: async (values: SettingsValues) => {
            const body = SettingsUpdateSchema.parse({values})
            const response = await fetch(settingsUrl(), {
                method: 'PUT',
                credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            })
            return readSettings(response, 'Failed to save settings')
        },
        onSuccess: (settings) => {
            queryClient.setQueryData(['settings'], settings)
        },
    })
}

export function useResetSettings() {
    const queryClient = useQueryClient()
    return useMutation({
        mutationFn: async () => {
            const response = await fetch(settingsUrl(), {
                method: 'DELETE',
                credentials: 'include',
            })
            return readSettings(response, 'Failed to reset settings')
        },
        onSuccess: (settings) => {
            queryClient.setQueryData(['settings'], settings)
        },
    })
}
