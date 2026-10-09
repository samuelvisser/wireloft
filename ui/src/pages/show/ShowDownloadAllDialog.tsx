import {useEffect, useId, useMemo, useState} from 'react'
import {Controller, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import Select from 'react-select'
import toast from 'react-hot-toast'
import {z} from 'zod'

import ConfirmDialog from '../../components/ConfirmDialog/ConfirmDialog'
import SimpleSelect from '../../components/common/SimpleSelect'
import {faIcon} from '../../icons/faIcon'
import {OperationStartError, useStartOperation} from '../../lib/operations'
import {EpisodeTypeReg} from '../../types/episode'
import {buildLocalMediaProfileSelectRegistry} from '../../types/local_media_profile'
import type {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import type {SeasonRead} from '../../types/schemas/season'
import {createSelectRegistry} from '../../utils/selectRegistry'
import './ShowDownloadAllDialog.css'

const LimitByReg = createSelectRegistry('DownloadAllLimitBy', {
  none: {label: 'No limits'},
  date: {label: 'Date'},
  episodes: {label: 'Number of episodes'},
})

const downloadAllFormSchema = z.object({
  localMediaProfileId: z.number().int().positive(),
  seasonIds: z.array(z.number().int().positive()),
  episodeTypes: z.array(z.string()),
  limitBy: z.enum(['none', 'date', 'episodes']),
  downloadDaysInPast: z.number().int().positive(),
  downloadEpisodeCount: z.number().int().positive(),
  downloadStartingFrom: z.iso.date().nullable(),
})

type DownloadAllForm = z.infer<typeof downloadAllFormSchema>

type Props = {
  showSlug: string
  showTitle: string
  showType: 'podcast' | 'series'
  seasons: readonly SeasonRead[]
  localMediaProfiles: readonly LocalMediaProfileRead[]
  onDismiss: () => void
}

export default function ShowDownloadAllDialog({
  showSlug,
  showTitle,
  showType,
  seasons,
  localMediaProfiles,
  onDismiss,
}: Props) {
  const selectId = useId()
  const startOperation = useStartOperation()
  const [starting, setStarting] = useState(false)

  const compatibleProfiles = useMemo(
    () => localMediaProfiles.filter((profile) => (
      profile.type === 'show'
      && (profile.showScope === 'both' || profile.showScope === showType)
    )),
    [localMediaProfiles, showType],
  )
  const profileRegistry = useMemo(
    () => buildLocalMediaProfileSelectRegistry(compatibleProfiles, 'show', showType),
    [compatibleProfiles, showType],
  )
  const seasonRegistry = useMemo(() => {
    const spec: Record<string, {label: string}> = {}
    const values: string[] = []
    for (const season of seasons) {
      const id = String(season.id)
      spec[id] = {label: season.name}
      values.push(id)
    }
    return createSelectRegistry('DownloadAllSeason', spec, values)
  }, [seasons])

  const schema = useMemo(
    () => downloadAllFormSchema.superRefine((data, context) => {
      if (showType === 'series' && data.seasonIds.length === 0) {
        context.addIssue({
          code: 'custom',
          path: ['seasonIds'],
          message: 'Select at least one season.',
        })
      }
      if (data.episodeTypes.length === 0) {
        context.addIssue({
          code: 'custom',
          path: ['episodeTypes'],
          message: 'Select at least one episode type.',
        })
      }
      if (showType === 'podcast' && data.limitBy === 'date' && data.downloadDaysInPast < 1) {
        context.addIssue({
          code: 'custom',
          path: ['downloadDaysInPast'],
          message: 'Enter a positive number of days.',
        })
      }
      if (showType === 'podcast' && data.limitBy === 'episodes' && data.downloadEpisodeCount < 1) {
        context.addIssue({
          code: 'custom',
          path: ['downloadEpisodeCount'],
          message: 'Enter a positive number of episodes.',
        })
      }
    }),
    [showType],
  )
  const {control, handleSubmit, setValue, watch, formState: {errors, dirtyFields}} = useForm<DownloadAllForm>({
    resolver: zodResolver(schema),
    defaultValues: {
      seasonIds: [],
      episodeTypes: [...EpisodeTypeReg.values],
      limitBy: 'none',
      downloadDaysInPast: 180,
      downloadEpisodeCount: 5,
      downloadStartingFrom: null,
    },
  })

  const limitBy = watch('limitBy')

  // Each selector initializes as its data arrives, without overwriting edits to another field.
  useEffect(() => {
    if (!dirtyFields.localMediaProfileId && compatibleProfiles[0]) {
      setValue('localMediaProfileId', compatibleProfiles[0].id)
    }
  }, [compatibleProfiles, dirtyFields.localMediaProfileId, setValue])

  useEffect(() => {
    if (!dirtyFields.seasonIds && seasons.length > 0) {
      setValue('seasonIds', seasons.map((season) => season.id))
    }
  }, [seasons, dirtyFields.seasonIds, setValue])

  const submit = handleSubmit(async (values) => {
    if (starting) return
    setStarting(true)
    try {
      const base = (window as any).appConfig?.API_URL || '/api'
      const result = await startOperation<{
        operationId: string
        queued: boolean
        episodesQueued: number
      }>(`${base}/shows/${encodeURIComponent(showSlug)}/download-all`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          localMediaProfileId: values.localMediaProfileId,
          seasonIds: showType === 'series' ? values.seasonIds : [],
          episodeTypes: values.episodeTypes,
          downloadDaysInPast: showType === 'podcast' && values.limitBy === 'date' ? values.downloadDaysInPast : 0,
          downloadEpisodeCount: showType === 'podcast' && values.limitBy === 'episodes' ? values.downloadEpisodeCount : 0,
          downloadStartingFrom: showType === 'podcast' && values.limitBy === 'none' ? values.downloadStartingFrom : null,
        }),
      })
      onDismiss()
      toast.success(result.queued
        ? `Queued ${result.episodesQueued} episode downloads for ${showTitle}`
        : `No new episodes to download for ${showTitle}`)
    } catch (error) {
      const detail = error instanceof OperationStartError ? error.message : undefined
      toast.error(detail || `Could not queue downloads for ${showTitle}`)
    } finally {
      setStarting(false)
    }
  })

  return (
    <ConfirmDialog
      open
      title="Download all episodes"
      onDismiss={() => {if (!starting) onDismiss()}}
      icon={faIcon('fas', 'download')}
      className="show-download-all-dialog"
      dismissOnOverlayClick={!starting}
      cancelButton={{disabled: starting}}
      confirmButton={{
        label: starting ? 'Starting…' : 'Download All',
        onClick: () => void submit(),
        disabled: starting || !compatibleProfiles.length,
      }}
    >
      <p>Download the selected episodes from "{showTitle}". Existing downloaded files will not be replaced.</p>
      <p>Downloads will wait for any countdown and configured post-publication delay before starting.</p>
      {showType === 'series' ? (
        <div className="form-row">
          <div className="show-download-all-label-row">
            <label htmlFor={`${selectId}-season`}>Seasons to download</label>
            <button
              type="button"
              className="btn btn-link"
              disabled={starting || seasons.length === 0}
              onClick={() => setValue('seasonIds', seasons.map((season) => season.id), {
                shouldDirty: true,
                shouldValidate: true,
              })}
            >
              Select all
            </button>
          </div>
          <Controller
            name="seasonIds"
            control={control}
            render={({field}) => (
              <Select
                inputId={`${selectId}-season`}
                classNamePrefix="select"
                isMulti
                options={seasonRegistry.options}
                value={seasonRegistry.options.filter((option) => field.value.includes(Number(option.value)))}
                onChange={(options) => field.onChange(options.map((option) => Number(option.value)))}
                onBlur={field.onBlur}
                closeMenuOnSelect={false}
                isDisabled={starting || seasons.length === 0}
                placeholder={seasons.length ? 'Select seasons' : 'No seasons available'}
                aria-invalid={!!errors.seasonIds}
              />
            )}
          />
          {errors.seasonIds && <div className="error" role="alert">{errors.seasonIds.message}</div>}
        </div>
      ) : null}
      <div className="form-row">
        <div className="show-download-all-label-row">
            <label htmlFor={`${selectId}-type`}>Episode types to download</label>
            <button
              type="button"
              className="btn btn-link"
              disabled={starting}
              onClick={() => setValue('episodeTypes', [...EpisodeTypeReg.values], {
                shouldDirty: true,
                shouldValidate: true,
              })}
            >
              Select all
            </button>
          </div>
          <Controller
            name="episodeTypes"
            control={control}
            render={({field}) => (
              <Select
                inputId={`${selectId}-type`}
                classNamePrefix="select"
                isMulti
                options={EpisodeTypeReg.options}
                value={EpisodeTypeReg.options.filter((option) => field.value.includes(option.value))}
                onChange={(options) => field.onChange(options.map((option) => option.value))}
                onBlur={field.onBlur}
                closeMenuOnSelect={false}
                isDisabled={starting}
                aria-invalid={!!errors.episodeTypes}
              />
            )}
          />
          {errors.episodeTypes && <div className="error" role="alert">{errors.episodeTypes.message}</div>}
      </div>
      {showType === 'podcast' && (
        <>
          <div className="form-row">
            <label htmlFor={`${selectId}-limit`}>Limit by</label>
            <Controller
              name="limitBy"
              control={control}
              render={({field}) => (
                <SimpleSelect
                  inputId={`${selectId}-limit`}
                  registry={LimitByReg}
                  value={field.value}
                  onChange={(value) => {
                    field.onChange(value)
                    if (value !== 'date') setValue('downloadDaysInPast', 180)
                    if (value !== 'episodes') setValue('downloadEpisodeCount', 5)
                    if (value !== 'none') setValue('downloadStartingFrom', null)
                  }}
                  onBlur={field.onBlur}
                  isDisabled={starting}
                />
              )}
            />
          </div>
          {limitBy === 'date' ? (
                <div className="form-row">
                  <label htmlFor={`${selectId}-days`}>Download days in past</label>
                  <Controller
                    name="downloadDaysInPast"
                    control={control}
                    render={({field}) => (
                      <input
                        {...field}
                        id={`${selectId}-days`}
                        className="input"
                        type="number"
                        min={1}
                        step={1}
                        disabled={starting}
                        onChange={(event) => field.onChange(event.currentTarget.valueAsNumber)}
                        aria-invalid={!!errors.downloadDaysInPast}
                      />
                    )}
                  />
                  {errors.downloadDaysInPast && (
                    <div className="error" role="alert">{errors.downloadDaysInPast.message}</div>
                  )}
                </div>
              ) : limitBy === 'episodes' ? (
                <div className="form-row">
                  <label htmlFor={`${selectId}-count`}>Latest episodes to download</label>
                  <Controller
                    name="downloadEpisodeCount"
                    control={control}
                    render={({field}) => (
                      <input
                        {...field}
                        id={`${selectId}-count`}
                        className="input"
                        type="number"
                        min={1}
                        step={1}
                        disabled={starting}
                        onChange={(event) => field.onChange(event.currentTarget.valueAsNumber)}
                        aria-invalid={!!errors.downloadEpisodeCount}
                      />
                    )}
                  />
                  {errors.downloadEpisodeCount && (
                    <div className="error" role="alert">{errors.downloadEpisodeCount.message}</div>
                  )}
                </div>
              ) : (
                <div className="form-row">
                  <label htmlFor={`${selectId}-start`}>Download starting from</label>
                  <Controller
                    name="downloadStartingFrom"
                    control={control}
                    render={({field}) => (
                      <input
                        id={`${selectId}-start`}
                        className="input"
                        type="date"
                        value={field.value ?? ''}
                        name={field.name}
                        onChange={(event) => field.onChange(event.target.value || null)}
                        onBlur={field.onBlur}
                        ref={field.ref}
                        disabled={starting}
                        aria-invalid={!!errors.downloadStartingFrom}
                      />
                    )}
                  />
                  <div className="help">Optional. Leave blank to include all eligible episodes.</div>
                </div>
              )}
        </>
      )}
      <div className="form-row">
        <label htmlFor={`${selectId}-profile`}>Local Media Profile</label>
        <Controller
          name="localMediaProfileId"
          control={control}
          render={({field}) => (
            <SimpleSelect
              inputId={`${selectId}-profile`}
              registry={profileRegistry}
              value={field.value ? String(field.value) : null}
              onChange={(value) => field.onChange(Number(value))}
              onBlur={field.onBlur}
              isDisabled={starting || compatibleProfiles.length === 0}
              placeholder={compatibleProfiles.length ? 'Select a profile' : 'No compatible Local Media Profiles'}
              aria-invalid={!!errors.localMediaProfileId}
            />
          )}
        />
        {errors.localMediaProfileId && (
          <div className="error" role="alert">Select a Local Media Profile.</div>
        )}
      </div>
    </ConfirmDialog>
  )
}
