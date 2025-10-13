import {useCallback, useEffect, useMemo, useState} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate, useParams} from 'react-router-dom'
import {useLocalMediaProfiles, usePodcastDownloadProfiles, useSeriesDownloadProfiles, useShows} from '../../lib/queries'
import DownloadProfileForm, {DownloadProfileMode} from '../../components/DownloadProfile/DownloadProfileForm'
import {PodcastDownloadProfileRead, PodcastDownloadProfileUpdateIn, PodcastDownloadProfileUpdateSchema} from '../../types/schemas/podcast_download_profile'
import {SeriesDownloadProfileRead, SeriesDownloadProfileUpdateIn, SeriesDownloadProfileUpdateSchema} from '../../types/schemas/series_download_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'


type RouteParams = { type?: DownloadProfileMode; id?: string }

type AnyUpdate = PodcastDownloadProfileUpdateIn | SeriesDownloadProfileUpdateIn

export default function EditDownloadProfilePage() {
  const { type, id } = useParams<RouteParams>()
  const navigate = useNavigate()

  const mode: DownloadProfileMode | undefined = (type === 'podcast' || type === 'series') ? type : undefined
  const profileId = id ? Number(id) : undefined

  const { data: shows } = useShows()
  const { data: mediaProfiles } = useLocalMediaProfiles()
  const { refetch: refetchPod } = usePodcastDownloadProfiles()
  const { refetch: refetchSer } = useSeriesDownloadProfiles()

  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [showName, setShowName] = useState<string>('')

  const formPodcast = useForm<PodcastDownloadProfileUpdateIn>({
    resolver: zodResolver(PodcastDownloadProfileUpdateSchema),
    mode: 'onBlur',
    shouldFocusError: true,
    defaultValues: {
      localMediaProfileId: (mediaProfiles?.[0] as LocalMediaProfileRead | undefined)?.id ?? 0,
      enableProfile: true,
      downloadWithCountdown: false,
      redownloadFinal: true,
      downloadDaysInPast: 180,
      deleteOlderEpisodes: true,
    },
  })

  const formSeries = useForm<SeriesDownloadProfileUpdateIn>({
    resolver: zodResolver(SeriesDownloadProfileUpdateSchema),
    mode: 'onBlur',
    shouldFocusError: true,
    defaultValues: {
      localMediaProfileId: (mediaProfiles?.[0] as LocalMediaProfileRead | undefined)?.id ?? 0,
      enableProfile: true,
      seasons: [],
      includeUpcomingSeasons: true,
    },
  })

  const form = (mode === 'podcast' ? formPodcast : formSeries) as any

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!mode || !profileId) {
        setError('Profile not found')
        setLoading(false)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const base = (window as any).appConfig.API_URL
        const endpoint = mode === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'
        const r = await fetch(`${base}/${endpoint}/${profileId}`, { credentials: 'include' })
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()

        if (mode === 'podcast') {
          const p = data as PodcastDownloadProfileRead
          if (!cancelled) {
            formPodcast.reset({
              localMediaProfileId: p.localMediaProfileId ?? 0,
              enableProfile: p.enableProfile,
              downloadWithCountdown: (p as any).downloadWithCountdown,
              redownloadFinal: (p as any).redownloadFinal,
              downloadDaysInPast: (p as any).downloadDaysInPast,
              deleteOlderEpisodes: (p as any).deleteOlderEpisodes,
            })
          }
          // Show name lookup by id
          const s = Array.isArray(shows) ? (shows as any[]).find((x) => (x as any).id === p.showId) : undefined
          if (s && typeof (s as any).name === 'string') setShowName((s as any).name)
          else setShowName(String(p.showId))
        } else {
          const s = data as SeriesDownloadProfileRead
          if (!cancelled) {
            formSeries.reset({
              localMediaProfileId: s.localMediaProfileId ?? 0,
              enableProfile: s.enableProfile,
              seasons: s.seasons ?? [],
              includeUpcomingSeasons: s.includeUpcomingSeasons ?? true,
            })
          }
          const sh = Array.isArray(shows) ? (shows as any[]).find((x) => (x as any).id === s.showId) : undefined
          if (sh && typeof (sh as any).name === 'string') setShowName((sh as any).name)
          else setShowName(String(s.showId))
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'Failed to load profile')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [mode, profileId, shows])

  const onCancel = useCallback(() => navigate('/download-profiles'), [navigate])

  const submitFn = async (data: AnyUpdate) => {
    if (!mode || !profileId) return undefined as any
    const base = (window as any).appConfig.API_URL
    const endpoint = mode === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'
    return fetch(`${base}/${endpoint}/${profileId}` , {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    })
  }

  const onSuccess = async () => {
    await Promise.all([refetchPod(), refetchSer()])
    navigate('/download-profiles')
  }

  const onSubmit = buildServerAwareSubmit(form as any, async (dataOut: AnyUpdate) => {
    const res = await submitFn(dataOut)
    if (res?.ok) await onSuccess()
    return res
  })

  const { formState: { isSubmitting } } = form

  if (!mode || !profileId) {
    return (
      <section className="view" aria-labelledby="edit-download-profile-title">
        <div className="view-header">
          <h1 id="edit-download-profile-title">Edit download profile</h1>
        </div>
        <p>Profile not found.</p>
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="button" className="btn" onClick={() => navigate('/download-profiles')}>Back</button>
        </div>
      </section>
    )
  }

  return (
    <section className="view" aria-labelledby="edit-download-profile-title">
      <div className="view-header">
        <h1 id="edit-download-profile-title">Edit download profile</h1>
      </div>

      {loading ? (
        <p>Loading…</p>
      ) : error ? (
        <p>{error}</p>
      ) : (
        <form className="form" onSubmit={onSubmit} noValidate>
          <div className="form-row">
            <label>Profile type</label>
            <div style={{ padding: '6px 0' }}>{mode === 'podcast' ? 'Podcast' : 'Series'}</div>
          </div>

          <div className="form-row">
            <label>Show</label>
            <div style={{ padding: '6px 0' }}>{showName}</div>
          </div>

          <div className="form-row">
            <label htmlFor="local-media-profile">Local Media Profile</label>
            <select
              id="local-media-profile"
              className="input"
              value={String((form.watch('localMediaProfileId') as any) ?? '')}
              onChange={(e) => form.setValue('localMediaProfileId' as any, Number(e.target.value), { shouldDirty: true, shouldValidate: true })}
              disabled={!mediaProfiles || mediaProfiles.length === 0}
            >
              {!mediaProfiles ? (
                <option>Loading profiles...</option>
              ) : mediaProfiles.length === 0 ? (
                <option>No profiles found</option>
              ) : (
                mediaProfiles.map((p) => (
                  <option key={(p as LocalMediaProfileRead).id} value={(p as LocalMediaProfileRead).id}>{(p as LocalMediaProfileRead).name}</option>
                ))
              )}
            </select>
          </div>

          <DownloadProfileForm form={form as any} mode={mode} seasons={[]} />

          <div className="actions">
            <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting} />
          </div>
        </form>
      )}
    </section>
  )
}
