import type {Versioned} from '../../types/data'
import {getCurrentAppVersion} from '../../utils/helpers'
import type {LocalMediaProfileMode} from './LocalMediaProfileForm'

export type LocalMediaProfileDraft<T> = {
    mode: LocalMediaProfileMode
    values: Partial<T>
}

const DRAFT_SCHEMA_VERSION = 'local-media-profile-v1'

function currentDraftVersion(): string {
    return `${getCurrentAppVersion() ?? 'development'}:${DRAFT_SCHEMA_VERSION}`
}

export function addLocalMediaProfileDraftKey(): string {
    return 'localMediaProfileDraft:add'
}

export function editLocalMediaProfileDraftKey(slug: string): string {
    return `localMediaProfileDraft:edit:${slug}`
}

export function loadLocalMediaProfileDraft<T>(key: string): LocalMediaProfileDraft<T> | null {
    try {
        const raw = localStorage.getItem(key)
        if (!raw) return null
        const parsed = JSON.parse(raw) as Versioned<LocalMediaProfileDraft<T>>
        if (parsed?.version !== currentDraftVersion() || !parsed.data?.values) {
            localStorage.removeItem(key)
            return null
        }
        if (parsed.data.mode !== 'show' && parsed.data.mode !== 'movie') {
            localStorage.removeItem(key)
            return null
        }
        return parsed.data
    } catch {
        return null
    }
}

export function saveLocalMediaProfileDraft<T>(key: string, draft: LocalMediaProfileDraft<T>): void {
    try {
        const payload: Versioned<LocalMediaProfileDraft<T>> = {
            version: currentDraftVersion(),
            data: draft,
        }
        localStorage.setItem(key, JSON.stringify(payload))
    } catch {
        // Draft persistence must never prevent editing the form.
    }
}

export function clearLocalMediaProfileDraft(key: string): void {
    try {
        localStorage.removeItem(key)
    } catch {
        // Ignore unavailable or full browser storage.
    }
}
