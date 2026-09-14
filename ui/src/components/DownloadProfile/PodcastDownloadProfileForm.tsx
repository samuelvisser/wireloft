import {Controller, UseFormReturn} from 'react-hook-form'
import Switch from 'react-switch'
import ReadMore from '../../utils/ReadMore'

type Props = {
    form: UseFormReturn<any>
    mode?: 'create' | 'update'
}

type LimitMode = 'none' | 'date' | 'episodes'

export default function PodcastDownloadProfileForm({form}: Props) {
    const {control, register, watch, setValue, formState: {errors}} = form

    // If countdown is disabled, redownload final becomes irrelevant and is hidden
    const withCountdown = watch('downloadWithCountdown')

    const watchedDaysRaw = watch('downloadDaysInPast') ?? 0
    const watchedEpisodeCountRaw = watch('downloadEpisodeCount') ?? 0
    const watchedDays = Number.isFinite(watchedDaysRaw) ? watchedDaysRaw : 0
    const watchedEpisodeCount = Number.isFinite(watchedEpisodeCountRaw) ? watchedEpisodeCountRaw : 0
    const daysInputInvalid = typeof watchedDaysRaw === 'number' && Number.isNaN(watchedDaysRaw)
    const episodeCountInputInvalid = typeof watchedEpisodeCountRaw === 'number' && Number.isNaN(watchedEpisodeCountRaw)
    const limitMode: LimitMode = watchedEpisodeCount > 0 || episodeCountInputInvalid
        ? 'episodes'
        : watchedDays > 0 || daysInputInvalid
            ? 'date'
            : 'none'

    const updateLimitMode = (mode: LimitMode) => {
        if (mode === 'none') {
            setValue('downloadDaysInPast', 0, {shouldDirty: true, shouldValidate: true})
            setValue('downloadEpisodeCount', 0, {shouldDirty: true, shouldValidate: true})
            return
        }

        setValue('downloadStartingFrom', null, {shouldDirty: true, shouldValidate: true})

        if (mode === 'date') {
            setValue('downloadEpisodeCount', 0, {shouldDirty: true, shouldValidate: true})
            setValue('downloadDaysInPast', watchedDays > 0 ? watchedDays : 180, {shouldDirty: true, shouldValidate: true})
            return
        }

        setValue('downloadDaysInPast', 0, {shouldDirty: true, shouldValidate: true})
        setValue('downloadEpisodeCount', watchedEpisodeCount > 0 ? watchedEpisodeCount : 5, {
            shouldDirty: true,
            shouldValidate: true,
        })
    }

    const oldestDateText = (() => {
        if (limitMode !== 'date' || !watchedDays || watchedDays <= 0) return null
        const d = new Date()
        d.setHours(0, 0, 0, 0)
        d.setDate(d.getDate() - watchedDays)
        const yyyy = d.getFullYear()
        const mm = String(d.getMonth() + 1).padStart(2, '0')
        const dd = String(d.getDate()).padStart(2, '0')
        return `${yyyy}-${mm}-${dd}`
    })()

    return (
        <>
            <div className="form-row">
                <label htmlFor="with-countdown">Download with countdown</label>
                <Controller
                    control={control}
                    name="downloadWithCountdown"
                    render={({field}) => (
                        <Switch
                            id="with-countdown"
                            checked={!!field.value}
                            onChange={(checked) => field.onChange(checked)}
                            onColor="#0ea5e9"
                            offColor="#d1d5db"
                            uncheckedIcon={false}
                            checkedIcon={false}
                            aria-invalid={!!errors.downloadWithCountdown}
                            aria-describedby={errors.downloadWithCountdown ? 'with-countdown-errors' : 'with-countdown-help'}
                        />
                    )}
                />
                {errors.downloadWithCountdown && (
                    <div id="with-countdown-errors" className="error" role="alert" aria-live="polite">
                        {errors.downloadWithCountdown.message as string}
                    </div>
                )}
                <div className="help" id="with-countdown-help">
                    <ReadMore summary={<span>Download with the countdown meant for live shows</span>}>
                        Some DailyWire podcast episodes appear with a countdown timer before the final media is available. Enabling
                        this option will download the episode while the countdown is still present. If enabled, you may also choose
                        to re-download the final version after the countdown disappears (usually in about 1,5 to 2 hours after
                        the episode was published).
                    </ReadMore>
                </div>
            </div>

            {withCountdown && (
                <div className="form-row">
                    <label htmlFor="redownload-final">Redownload final version</label>
                    <Controller
                        control={control}
                        name="redownloadFinal"
                        render={({field}) => (
                            <Switch
                                id="redownload-final"
                                checked={!!field.value}
                                onChange={(checked) => field.onChange(checked)}
                                onColor="#0ea5e9"
                                offColor="#d1d5db"
                                uncheckedIcon={false}
                                checkedIcon={false}
                                aria-invalid={!!errors.redownloadFinal}
                                aria-describedby={errors.redownloadFinal ? 'redownload-final-errors' : undefined}
                            />
                        )}
                    />
                    {errors.redownloadFinal && (
                        <div id="redownload-final-errors" className="error" role="alert" aria-live="polite">
                            {errors.redownloadFinal.message as string}
                        </div>
                    )}
                </div>
            )}

            <div className="form-row">
                <label htmlFor="download-limit-mode">Limit by</label>
                <select
                    id="download-limit-mode"
                    className="input"
                    value={limitMode}
                    onChange={(event) => updateLimitMode(event.target.value as LimitMode)}
                >
                    <option value="none">No limits</option>
                    <option value="date">Date</option>
                    <option value="episodes">Number of episodes</option>
                </select>
                <div className="help">
                    Choose whether to use no rolling limit, a rolling date window, or only the latest number of episodes.
                </div>
            </div>

            {limitMode === 'none' && (
                <div className="form-row">
                    <label htmlFor="download-starting-from">Download starting from</label>
                    <Controller
                        control={control}
                        name="downloadStartingFrom"
                        render={({field}) => (
                            <input
                                id="download-starting-from"
                                className="input"
                                type="date"
                                name={field.name}
                                value={field.value ?? ''}
                                onChange={(event) => field.onChange(event.target.value || null)}
                                onBlur={field.onBlur}
                                ref={field.ref}
                                aria-invalid={!!errors.downloadStartingFrom}
                                aria-describedby={errors.downloadStartingFrom ? 'download-starting-from-errors' : 'download-starting-from-help'}
                            />
                        )}
                    />
                    {errors.downloadStartingFrom && (
                        <div id="download-starting-from-errors" className="error" role="alert" aria-live="polite">
                            {errors.downloadStartingFrom.message as string}
                        </div>
                    )}
                    <div className="help" id="download-starting-from-help">
                        Optional. Download eligible episodes published on or after this date and keep downloading new episodes.
                        Existing downloads are not removed. Leave blank to download everything.
                    </div>
                </div>
            )}

            {limitMode === 'date' && (
                <div className="form-row">
                    <label htmlFor="days-in-past">Download days in past</label>
                    <input
                        id="days-in-past"
                        className="input"
                        type="number"
                        inputMode="numeric"
                        min={1}
                        step={1}
                        {...register('downloadDaysInPast', {valueAsNumber: true})}
                        aria-invalid={!!errors.downloadDaysInPast}
                        aria-describedby={errors.downloadDaysInPast ? 'days-in-past-errors' : 'days-in-past-help'}
                    />
                    {errors.downloadDaysInPast && (
                        <div id="days-in-past-errors" className="error" role="alert" aria-live="polite">
                            {errors.downloadDaysInPast.message as string}
                        </div>
                    )}
                    <div className="help" id="days-in-past-help">
                        Amount of days in the past the show should be downloaded.
                        {oldestDateText ? (
                            <>
                                {' '}Earliest date that will be downloaded: <strong>{oldestDateText}</strong>
                            </>
                        ) : null}
                    </div>
                </div>
            )}

            {limitMode === 'episodes' && (
                <div className="form-row">
                    <label htmlFor="episode-count">Latest episodes to download</label>
                    <input
                        id="episode-count"
                        className="input"
                        type="number"
                        inputMode="numeric"
                        min={1}
                        step={1}
                        {...register('downloadEpisodeCount', {valueAsNumber: true})}
                        aria-invalid={!!errors.downloadEpisodeCount}
                        aria-describedby={errors.downloadEpisodeCount ? 'episode-count-errors' : 'episode-count-help'}
                    />
                    {errors.downloadEpisodeCount && (
                        <div id="episode-count-errors" className="error" role="alert" aria-live="polite">
                            {errors.downloadEpisodeCount.message as string}
                        </div>
                    )}
                    <div className="help" id="episode-count-help">
                        Only the latest number of eligible episodes will be downloaded by this profile.
                    </div>
                </div>
            )}

            {limitMode !== 'none' && (
                <div className="form-row">
                    <label htmlFor="delete-older">Delete older episodes</label>
                    <Controller
                        control={control}
                        name="deleteOlderEpisodes"
                        render={({field}) => (
                            <Switch
                                id="delete-older"
                                checked={!!field.value}
                                onChange={(checked) => field.onChange(checked)}
                                onColor="#0ea5e9"
                                offColor="#d1d5db"
                                uncheckedIcon={false}
                                checkedIcon={false}
                                aria-invalid={!!errors.deleteOlderEpisodes}
                                aria-describedby={errors.deleteOlderEpisodes ? 'delete-older-errors' : 'delete-older-help'}
                            />
                        )}
                    />
                    {errors.deleteOlderEpisodes && (
                        <div id="delete-older-errors" className="error" role="alert" aria-live="polite">
                            {errors.deleteOlderEpisodes.message as string}
                        </div>
                    )}
                    <div className="help" id="delete-older-help">
                        <ReadMore summary={<span>Whether to delete episodes outside the selected limit</span>}>
                            {limitMode === 'date'
                                ? 'If enabled, downloaded episodes older than the date shown above will be automatically removed from disk.'
                                : `If enabled, downloaded episodes outside the latest ${watchedEpisodeCount || 'selected number of'} eligible episodes will be automatically removed from disk.`}
                        </ReadMore>
                    </div>
                </div>
            )}
        </>
    )
}
