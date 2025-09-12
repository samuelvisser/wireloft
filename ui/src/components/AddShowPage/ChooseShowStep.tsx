import {useEffect, useState} from 'react'

type Props = {
    rawUrl: string
    onChangeRawUrl: (v: string) => void
    urlValid: boolean
    showUrlErrors: boolean
    errors: string[]
    onContinue: () => void
    onCancel: () => void
    slug?: string
}

import DailywireShowCard from './DailywireShowCard'
import {useDailywireShow} from '../../lib/queries'
import ReadMore from '../../utils/ReadMore'

export default function ChooseShowStep({
                                    rawUrl,
                                    onChangeRawUrl,
                                    urlValid,
                                    showUrlErrors,
                                    errors,
                                    onContinue,
                                    onCancel,
                                    slug
                                }: Props) {
    const dw = useDailywireShow(slug)

    // Show type selection (Podcast/Series)
    const [showType, setShowType] = useState<string>('')

    // Initialize from API probableShowType when data loads/changes
    useEffect(() => {
        const anyData = dw.data as any
        const v = (anyData?.probableShowType ?? anyData?.probable_show_type) as string | undefined
        if (v === 'podcast' || v === 'series') {
            setShowType(v)
        } else {
            setShowType('')
        }
    }, [dw.data])

    // Episode identification selection (Date-based/Numbered), only relevant to podcasts
    const [episodeIdentification, setEpisodeIdentification] = useState<string>('')

    // Initialize from API probableEpisodeIdentification when data loads/changes
    useEffect(() => {
        const anyData = dw.data as any
        const v = (anyData?.probableEpisodeIdentification ?? anyData?.probable_episode_identification) as string | undefined
        if (v === 'date_based' || v === 'numbered') {
            setEpisodeIdentification(v)
        } else {
            setEpisodeIdentification('')
        }
    }, [dw.data])

    const episodeIdOk = showType !== 'podcast' || episodeIdentification !== ''
    const canContinue = urlValid && !!slug && dw.isSuccess && !!dw.data && showType !== '' && episodeIdOk

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
                    value={rawUrl}
                    onChange={(e) => onChangeRawUrl(e.target.value)}
                    aria-invalid={showUrlErrors && !urlValid}
                    aria-describedby="url-help url-errors"
                />
                <div id="url-help" className="help">
                    Must be on dailywire.com, include /show/, and a show name.
                </div>
                {showUrlErrors && errors.length > 0 && (
                    <ul id="url-errors" className="error-list" role="alert">
                        {errors.map((msg, i) => (
                            <li key={i}>{msg}</li>
                        ))}
                    </ul>
                )}
            </div>

            {/* Preview fetched DailyWire show info */}
            {urlValid && (
                <>
                    <div className="form-row" aria-live="polite">
                        <DailywireShowCard slug={slug} />
                    </div>

                    {/* Show type selector under the card */}
                    {dw.isSuccess && !!dw.data && (
                        <>
                            <div className="form-row">
                                <label htmlFor="show-type">Show type</label>
                                <select
                                    id="show-type"
                                    className="input"
                                    value={showType}
                                    onChange={(e) => setShowType(e.target.value)}
                                >
                                    <option value="">Select a type…</option>
                                    <option value="podcast">Podcast</option>
                                    <option value="series">Series</option>
                                </select>
                                <div className="help" id="show-type-help">
                                    <ReadMore summary={<span>Why do I need to choose this?</span>}>
                                        Selecting the correct show type helps WireLoft apply sensible defaults for how
                                        episodes are grouped and presented.
                                    </ReadMore>
                                </div>
                            </div>

                            {/* Episode identification selector (only for Podcast) */}
                            {showType === 'podcast' && (
                                <div className="form-row">
                                    <label htmlFor="episode-identification">Episode identification</label>
                                    <select
                                        id="episode-identification"
                                        className="input"
                                        value={episodeIdentification}
                                        onChange={(e) => setEpisodeIdentification(e.target.value)}
                                    >
                                        <option value="">Select episode identification…</option>
                                        <option value="date_based">Date-based</option>
                                        <option value="numbered">Numbered</option>
                                    </select>
                                    <div className="help" id="show-type-help">
                                        <ReadMore summary={<span>How are episodes in this show identified?</span>}>
                                            Some shows identify their episodes by a number. In this case, WireLoft expects to see
                                            a string "Ep. " in the title. The number that follows it, is taken as the episode number.
                                            Episodes without this format will be regarded as auxiliary content.<br/><br/>
                                            Sometimes however, shows use a date-based format. In this case, the episodes are identified
                                            simply by their release date.<br/><br/>
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
