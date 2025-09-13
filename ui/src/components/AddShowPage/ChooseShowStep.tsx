import {useEffect, useMemo, useState} from 'react'

export type ShowFormValue = {
    rawUrl: string
    showType: 'podcast' | 'series' | null
    episodeIdentifier: 'date_based' | 'numbered' | null
}

type Props = {
    value: ShowFormValue
    onChange: (v: ShowFormValue) => void
    onContinue: () => void
    onCancel: () => void
    onSlugChange?: (slug?: string) => void
}

import DailywireShowCard from './DailywireShowCard'
import {useDailywireShow} from '../../lib/queries'
import ReadMore from '../../utils/ReadMore'

// Local helpers for URL validation and normalization (moved from parent)

type ValidationResult = {
    domainOk: boolean
    pathOk: boolean
    slugOk: boolean
    errors: string[]
    normalized?: string
}

function ensureProtocol(input: string): string {
    let v = input.trim()
    if (!v) return v
    // If the string doesn't start with a URL scheme, prepend https://
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)) {
        v = 'https://' + v
    }
    return v
}

function validateShowUrl(input: string): ValidationResult {
    const withProto = ensureProtocol(input)
    try {
        const url = new URL(withProto)
        const host = url.hostname.toLowerCase()
        const domainOk = host === 'dailywire.com' || host === 'www.dailywire.com'
        const path = url.pathname
        const pathOk = path.startsWith('/show/')
        let slugOk = false
        if (pathOk) {
            const slug = path.slice('/show/'.length).split('/')[0]
            slugOk = !!slug
        }
        const errors: string[] = []
        if (!domainOk) errors.push('URL must be on dailywire.com')
        if (!pathOk) errors.push('URL must include /show/ in the path')
        if (!slugOk) errors.push('URL must include a show name after /show/ (e.g., the-ben-shapiro-show)')
        return {domainOk, pathOk, slugOk, errors, normalized: url.toString()}
    } catch {
        return {
            domainOk: false,
            pathOk: false,
            slugOk: false,
            errors: [
                'URL must be on dailywire.com',
                'URL must include /show/ in the path',
                'URL must include a show name after /show/ (e.g., the-ben-shapiro-show)',
            ],
        }
    }
}

export default function ChooseShowStep({
                                           value,
                                           onChange,
                                           onContinue,
                                           onCancel,
                                           onSlugChange,
                                       }: Props) {
    // Validate URL locally
    const result = useMemo(() => validateShowUrl(value.rawUrl), [value.rawUrl])
    const urlValid = result.domainOk && result.pathOk && result.slugOk
    const showUrlErrors = value.rawUrl.trim().length > 0

    // Extract DailyWire show slug from the URL when valid
    const showSlug = useMemo(() => {
        if (!urlValid) return undefined
        try {
            const u = new URL(result.normalized ?? ensureProtocol(value.rawUrl))
            const path = u.pathname
            if (!path.startsWith('/show/')) return undefined
            const s = path.slice('/show/'.length).split('/')[0]
            return s || undefined
        } catch {
            return undefined
        }
    }, [urlValid, value.rawUrl, result.normalized])

    // Debounce to detect "done typing"
    const [debouncedSlug, setDebouncedSlug] = useState<string | undefined>(undefined)
    useEffect(() => {
        const h = setTimeout(() => setDebouncedSlug(showSlug), 500)
        return () => clearTimeout(h)
    }, [showSlug])

    // Notify parent of slug changes for later wizard steps
    useEffect(() => {
        onSlugChange?.(debouncedSlug)
    }, [debouncedSlug, onSlugChange])

    const dw = useDailywireShow(debouncedSlug)

    // Initialize from API probable values when data loads/changes, but only if missing in current value
    useEffect(() => {
        const anyData = dw.data as any
        const v = (anyData?.probableShowType ?? anyData?.probable_show_type) as string | undefined
        if (!value.showType && (v === 'podcast' || v === 'series')) {
            onChange({ ...value, showType: v as 'podcast' | 'series' })
        }
    }, [dw.data])

    useEffect(() => {
        const anyData = dw.data as any
        const v = (anyData?.probableEpisodeIdentification ?? anyData?.probable_episode_identification) as string | undefined
        if (value.showType === 'podcast' && !value.episodeIdentifier && (v === 'date_based' || v === 'numbered')) {
            onChange({ ...value, episodeIdentifier: v as 'date_based' | 'numbered' })
        }
    }, [dw.data, value.showType, value.episodeIdentifier])

    const episodeIdOk = value.showType !== 'podcast' || value.episodeIdentifier !== null
    const canContinue = urlValid && !!debouncedSlug && dw.isSuccess && !!dw.data && value.showType !== null && episodeIdOk

    return (
        <form className="form" onSubmit={(e) => e.preventDefault()} noValidate>
            <div className="form-row">
                <label htmlFor="show-url">Daily Wire show URL</label>
                <input
                    id="show-url"
                    className="input"
                    type="url"
                    inputMode="url"
                    autoFocus
                    placeholder="https://www.dailywire.com/show/the-ben-shapiro-show"
                    value={value.rawUrl}
                    onChange={(e) => onChange({ ...value, rawUrl: e.target.value })}
                    aria-invalid={showUrlErrors && !urlValid}
                    aria-describedby="url-help url-errors"
                />
                <div id="url-help" className="help">
                    Must be on dailywire.com, include /show/, and a show name.
                </div>
                {showUrlErrors && result.errors.length > 0 && (
                    <ul id="url-errors" className="error-list" role="alert">
                        {result.errors.map((msg, i) => (
                            <li key={i}>{msg}</li>
                        ))}
                    </ul>
                )}
            </div>

            {/* Preview fetched DailyWire show info */}
            {urlValid && (
                <>
                    <div className="form-row" aria-live="polite">
                        <DailywireShowCard slug={debouncedSlug} />
                    </div>

                    {/* Show type selector under the card */}
                    {dw.isSuccess && !!dw.data && (
                        <>
                            <div className="form-row">
                                <label htmlFor="show-type">Show type</label>
                                <select
                                    id="show-type"
                                    className="input"
                                    value={value.showType ?? ''}
                                    onChange={(e) => {
                                        const v = e.target.value as 'podcast' | 'series' | ''
                                        const nextType = v === '' ? null : (v as 'podcast' | 'series')
                                        const nextEpisodeId = nextType === 'series' ? null : value.episodeIdentifier
                                        onChange({ ...value, showType: nextType, episodeIdentifier: nextEpisodeId })
                                    }}
                                >
                                    <option value="">Select a type…</option>
                                    <option value="podcast">Podcast</option>
                                    <option value="series">Series</option>
                                </select>
                                <div className="help" id="show-type-help">
                                    <ReadMore summary={<span>Why do I need to choose this?</span>}>
                                        Selecting the correct show type helps WireLoft apply sensible defaults for how
                                        episodes are grouped and presented.<br /><br />
                                        Though WireLoft tries to guess the show type automatically based on various
                                        factors,
                                        Dailywire unfortunately does not provide a reliable way to determine this.
                                        If you're unsure, select "Podcast".
                                    </ReadMore>
                                </div>
                            </div>

                            {/* Episode identification selector (only for Podcast) */}
                            {value.showType === 'podcast' && (
                                <div className="form-row">
                                    <label htmlFor="episode-identification">Episode identification</label>
                                    <select
                                        id="episode-identification"
                                        className="input"
                                        value={value.episodeIdentifier ?? ''}
                                        onChange={(e) => {
                                            const v = e.target.value as 'date_based' | 'numbered' | ''
                                            onChange({ ...value, episodeIdentifier: v === '' ? null : (v as 'date_based' | 'numbered') })
                                        }}
                                    >
                                        <option value="">Select episode identification…</option>
                                        <option value="date_based">Date-based</option>
                                        <option value="numbered">Numbered</option>
                                    </select>
                                    <div className="help" id="show-type-help">
                                        <ReadMore summary={<span>How are episodes in this show identified?</span>}>
                                            Some shows identify their episodes by a number. In this case, WireLoft
                                            expects to see
                                            a string "Ep. " in the title. The number that follows it, is taken as the
                                            episode number.
                                            Episodes without this format will be regarded as auxiliary
                                            content.<br /><br />
                                            Sometimes however, shows use a date-based format. In this case, the episodes
                                            are identified
                                            simply by their release date.<br /><br />
                                            If you're unsure, select "Date-based".
                                        </ReadMore>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </>
            )}

            <div className="actions">
                <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => canContinue && onContinue()}
                    disabled={!canContinue}
                >
                    Continue
                </button>
                <button type="button" className="btn" onClick={onCancel}>
                    Cancel
                </button>
            </div>
        </form>
    )
}
