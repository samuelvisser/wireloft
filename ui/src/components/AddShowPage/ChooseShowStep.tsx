import {useEffect, useMemo, useState} from 'react'
import DailywireShowCard from './DailywireShowCard'
import {useDailywireShow} from '../../lib/queries'
import ReadMore from '../../utils/ReadMore'
import {useForm} from "react-hook-form";
import {WithRoot} from "../../types/form";
import {zodResolver} from "@hookform/resolvers/zod";
import {ShowCreate, ShowCreateSchema} from "../../types/schemas/show";
import {buildServerAwareSubmit} from "../../utils/buildServerAwareSubmit";
import {ShowType} from "../../types/show";


type Props = {
    onContinue: () => void
    onCancel: () => void
}

export default function ChooseShowStep({onContinue, onCancel}: Props) {

    const form = useForm<WithRoot<ShowCreate>>({
        resolver: zodResolver(ShowCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
    })
    const {register, formState: {isSubmitting, errors}} = form;


    const submitForm = async (data: ShowCreate) => {
        return data
    };
    const onSubmit = buildServerAwareSubmit(form, submitForm, {
        fallbackField: 'url',
        aliasToFallback: [
            'title', 'description', 'authorName', 'authorHeadshotPath', 'backgroundImagePath', 'logoImagePath', 'thumbnailLandscapePath', 'thumbnailPortraitPath', "thumbnailSquarePath", "dwId", "slug", "authorSlug"
        ]
    })


    const watchedUrl: string = form.watch('url');
    const urlParsed = useMemo(() => {
        return ShowCreateSchema.shape.url.safeParse(watchedUrl ?? '')
    }, [watchedUrl])
    const urlValid = urlParsed.success

    const slugFromUrl = useMemo(() => {
        console.log('Slug extractor runs...')

        if (!urlValid) return undefined

        try {
            const parsedUrl = new URL(urlParsed?.data ?? '')
            const path = parsedUrl.pathname

            if (!path.startsWith('/show/')) return undefined
            const s = path.slice('/show/'.length).split('/')[0]
            return s || undefined
        } catch {
            return undefined
        }
    }, [urlParsed])

    const dw = useDailywireShow(slugFromUrl)

    // Set form values when dailywire api returns data
    useEffect(() => {

        console.log(dw.data)

    }, [dw.data])

    // Set show type and episode identifier based on dailywire data
    const showTypeField = form.watch('type')
    const episodeIdentifierField = form.watch('episodeIdentifier')
    useEffect(() => {
        const anyData = dw.data as any
        const v = (anyData?.probableEpisodeIdentification ?? anyData?.probable_episode_identification) as string | undefined
        if (showTypeField === ShowType.podcast && episodeIdentifierField == null && (v === 'date_based' || v === 'numbered')) {
            onChange({...value, episodeIdentifier: v as 'date_based' | 'numbered'})
        }
        // Clear episodeIdentifier if switched to series
        if (value.type === 'series' && value.episodeIdentifier) {
            onChange({...value, episodeIdentifier: ''})
        }
    }, [dw.data, showTypeField, episodeIdentifierField])


    return (
        <form className="form" onSubmit={onSubmit} noValidate>
            <div className="form-row">
                <label htmlFor="show-url">Daily Wire show URL</label>
                <input
                    id="show-url"
                    className="input"
                    type="url"
                    inputMode="url"
                    placeholder="https://www.dailywire.com/show/the-ben-shapiro-show"
                    {...register('url')}
                    aria-invalid={!!errors.url}
                    aria-describedby={errors.url ? 'show-url-validate' : undefined}
                />
                {(errors.url) && (
                    <div id="mp-name-validate" className="error" role="alert" aria-live="polite">
                        {(errors.url)?.message}
                    </div>
                )}
                <div id="url-help" className="help">
                    Must be on dailywire.com, include /show/, and a show name.
                </div>
            </div>

            {/* Preview fetched DailyWire show info */}
            {urlValid && (
                <>
                    <div className="form-row" aria-live="polite">
                        <DailywireShowCard slug={slugFromUrl}/>
                    </div>

                    {/* Show type selector under the card */}
                    {dw.isSuccess && !!dw.data && (
                        <>
                            <div className="form-row">
                                <label htmlFor="show-type">Show type</label>
                                <select
                                    id="show-type"
                                    className="input"
                                    {...register('type')}
                                    aria-invalid={!!errors.type}
                                    aria-describedby={errors.type ? 'show-type-validate' : undefined}
                                >
                                    <option value="">Select a type…</option>
                                    <option value="podcast">Podcast</option>
                                    <option value="series">Series</option>
                                </select>
                                {(errors.type) && (
                                    <div id="mp-type-validate" className="error" role="alert" aria-live="polite">
                                        {(errors.type)?.message}
                                    </div>
                                )}
                                <div className="help" id="show-type-help">
                                    <ReadMore summary={<span>Why do I need to choose this?</span>}>
                                        Selecting the correct show type helps WireLoft apply sensible defaults for how
                                        episodes are grouped and presented.<br/><br/>
                                        Though WireLoft tries to guess the show type automatically based on various
                                        factors,
                                        Dailywire unfortunately does not provide a reliable way to determine this.
                                        If you're unsure, select "Podcast".
                                    </ReadMore>
                                </div>
                            </div>

                            {/* Episode identification selector (only for Podcast) */}
                            {showTypeField == ShowType.podcast && (
                                <div className="form-row">
                                    <label htmlFor="episode-identification">Episode identification</label>
                                    <select
                                        id="episode-identification"
                                        className="input"
                                        value={value.episodeIdentifier ?? ''}
                                        onChange={(e) => {
                                            const v = e.target.value as 'date_based' | 'numbered' | ''
                                            onChange({...value, episodeIdentifier: v === '' ? '' : v})
                                        }}
                                        aria-invalid={episodeIdErrors.length > 0}
                                        aria-describedby={episodeIdErrors.length ? 'episode-identification-errors' : undefined}
                                    >
                                        <option value="">Select episode identification…</option>
                                        <option value="date_based">Date-based</option>
                                        <option value="numbered">Numbered</option>
                                    </select>
                                    {episodeIdErrors.length > 0 && (
                                        <div id="episode-identification-errors" className="error" role="alert"
                                             aria-live="polite">
                                            {episodeIdErrors.join('\n')}
                                        </div>
                                    )}
                                    <div className="help" id="show-type-help">
                                        <ReadMore summary={<span>How are episodes in this show identified?</span>}>
                                            Some shows identify their episodes by a number. In this case, WireLoft
                                            expects to see
                                            a string "Ep. " in the title. The number that follows it, is taken as the
                                            episode number.
                                            Episodes without this format will be regarded as auxiliary
                                            content.<br/><br/>
                                            Sometimes however, shows use a date-based format. In this case, the episodes
                                            are identified
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
                <input type="submit" className="btn btn-primary" value="Continue" disabled={isSubmitting}/>
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    )
}
