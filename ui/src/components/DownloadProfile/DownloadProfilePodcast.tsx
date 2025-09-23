import {useEffect, useMemo} from 'react'
import {Controller, SubmitHandler, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import Switch from 'react-switch'
import ReadMore from '../../utils/ReadMore'
import {DownloadProfilePodcastCreateSchema, type DownloadProfilePodcastCreateOut} from '../../types/schemas/download_profile_podcast'

export type DownloadProfilePodcastForm = DownloadProfilePodcastCreateOut

export type DownloadProfilePodcastProps = {
  onBack: () => void
  onFinish: (data: DownloadProfilePodcastForm) => void
  onCancel: () => void
}

export default function DownloadProfilePodcast({ onBack, onFinish, onCancel }: DownloadProfilePodcastProps) {
  const form = useForm<DownloadProfilePodcastForm>({
    resolver: zodResolver(DownloadProfilePodcastCreateSchema),
    mode: 'onBlur',
    shouldFocusError: true,
    defaultValues: {
      // Note: showId is unknown in the wizard; use 0 as a placeholder (schema only requires a number)
      showId: 0,
      enableProfile: true,
      downloadWithCountdown: false,
      redownloadFinal: true,
      downloadDaysInPast: 180,
      deleteOlderEpisodes: true,
    },
  })

  const { control, register, watch, setValue, handleSubmit, formState: { errors, isSubmitting } } = form

  // If countdown is disabled, redownload final becomes irrelevant and is hidden
  const withCountdown = watch('downloadWithCountdown')
  useEffect(() => {
    if (!withCountdown) {
      setValue('redownloadFinal', true, { shouldDirty: true, shouldValidate: false })
    }
  }, [withCountdown, setValue])

  const watchedDays = watch('downloadDaysInPast') ?? 0
  const oldestDateText = useMemo(() => {
    const days = Number.isFinite(watchedDays) ? watchedDays : 0
    if (!days || days <= 0) return null
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() - days)
    const yyyy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd}`
  }, [watchedDays])

  const onSubmit: SubmitHandler<DownloadProfilePodcastForm> = (data) => {
    onFinish(data)
  }

  return (
    <form className="form form-fluid" onSubmit={handleSubmit(onSubmit)} noValidate>
      <div className="form-row">
        <label htmlFor="enable-profile">Enable automatic downloads</label>
        <Controller
          control={control}
          name="enableProfile"
          render={({ field }) => (
            <Switch
              id="enable-profile"
              checked={!!field.value}
              onChange={(checked) => field.onChange(checked)}
              onColor="#0ea5e9"
              offColor="#d1d5db"
              uncheckedIcon={false}
              checkedIcon={false}
              aria-invalid={!!errors.enableProfile}
              aria-describedby={errors.enableProfile ? 'enable-profile-errors' : undefined}
            />
          )}
        />
        {errors.enableProfile && (
          <div id="enable-profile-errors" className="error" role="alert" aria-live="polite">
            {errors.enableProfile.message as string}
          </div>
        )}
      </div>

      <div className="form-row">
        <label htmlFor="with-countdown">Download with countdown</label>
        <Controller
          control={control}
          name="downloadWithCountdown"
          render={({ field }) => (
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
          <ReadMore summary={<span>What does this mean?</span>}>
            Some DailyWire podcast episodes appear with a countdown timer before the final media is available. Enabling this option will download the episode while the countdown is still present. If enabled, you may also choose to re-download the final version after the countdown disappears.
          </ReadMore>
        </div>
      </div>

      {withCountdown && (
        <div className="form-row">
          <label htmlFor="redownload-final">Redownload final version</label>
          <Controller
            control={control}
            name="redownloadFinal"
            render={({ field }) => (
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
        <label htmlFor="days-in-past">Download days in past</label>
        <input
          id="days-in-past"
          className="input"
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          {...register('downloadDaysInPast', { valueAsNumber: true })}
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

      {(watchedDays ?? 0) > 0 && (
        <div className="form-row">
          <label htmlFor="delete-older">Delete older episodes</label>
          <Controller
            control={control}
            name="deleteOlderEpisodes"
            render={({ field }) => (
              <Switch
                id="delete-older"
                checked={!!field.value}
                onChange={(checked) => field.onChange(checked)}
                onColor="#0ea5e9"
                offColor="#d1d5db"
                uncheckedIcon={false}
                checkedIcon={false}
                aria-invalid={!!errors.deleteOlderEpisodes}
                aria-describedby={errors.deleteOlderEpisodes ? 'delete-older-errors' : undefined}
              />
            )}
          />
          {errors.deleteOlderEpisodes && (
            <div id="delete-older-errors" className="error" role="alert" aria-live="polite">
              {errors.deleteOlderEpisodes.message as string}
            </div>
          )}
        </div>
      )}

      <div className="actions">
        <button type="button" className="btn" onClick={onBack}>Back</button>
        <input type="submit" className="btn btn-primary" value="Finish" disabled={isSubmitting} />
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
