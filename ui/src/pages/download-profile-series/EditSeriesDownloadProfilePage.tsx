import {useCallback, useEffect, useState} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate, useParams} from 'react-router-dom'
import {useLocalMediaProfiles, useSeriesDownloadProfiles, useShows} from '../../lib/queries'
import DownloadProfileForm from '../../components/DownloadProfile/DownloadProfileForm'
import {SeriesDownloadProfileRead, SeriesDownloadProfileUpdateIn, SeriesDownloadProfileUpdateSchema} from '../../types/schemas/series_download_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'


type RouteParams = { id?: string }

export default function EditSeriesDownloadProfilePage() {
  const { id } = useParams<RouteParams>()
  const navigate = useNavigate()

  const profileId = id ? Number(id) : undefined

  const { data: shows } = useShows()
  const { data: mediaProfiles } = useLocalMediaProfiles()
  const { refetch: refetchSer } = useSeriesDownloadProfiles()

  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [showName, setShowName] = useState<string>('')

  const form = useForm<SeriesDownloadProfileUpdateIn>({
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

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!profileId) {
        setError('Profile not found')
        setLoading(false)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const base = (window as any).appConfig.API_URL
        const r = await fetch(`${base}/series-download-profiles/${profileId}`, { credentials: 'include' })
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()

        const s = data as SeriesDownloadProfileRead
        if (!cancelled) {
          form.reset({
            localMediaProfileId: s.localMediaProfileId ?? 0,
            enableProfile: s.enableProfile,
            seasons: s.seasons ?? [],
            includeUpcomingSeasons: s.includeUpcomingSeasons ?? true,
          })
        }
        const sh = Array.isArray(shows) ? (shows as any[]).find((x) => (x as any).id === s.showId) : undefined
        if (sh && typeof (sh as any).name === 'string') setShowName((sh as any).name)
        else setShowName(String(s.showId))
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'Failed to load profile')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [profileId, shows])

  const onCancel = useCallback(() => navigate('/download-profiles'), [navigate])

  const submitFn = async (data: SeriesDownloadProfileUpdateIn) => {
    if (!profileId) return undefined as any
    const base = (window as any).appConfig.API_URL
    return fetch(`${base}/series-download-profiles/${profileId}` , {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    })
  }

  const onSuccess = async () => {
    await Promise.all([refetchSer()])
    navigate('/download-profiles')
  }

  const onSubmit = buildServerAwareSubmit(form as any, async (dataOut: SeriesDownloadProfileUpdateIn) => {
    const res = await submitFn(dataOut)
    if (res?.ok) await onSuccess()
    return res
  })

  const { formState: { isSubmitting } } = form

  if (!profileId) {
    return (
      <section className="view" aria-labelledby="edit-download-profile-title">
        <div className="view-header">
          <h1 id="edit-download-profile-title">Edit series download profile</h1>
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
        <h1 id="edit-download-profile-title">Edit series download profile</h1>
      </div>

      {loading ? (
        <p>Loading…</p>
      ) : error ? (
        <p>{error}</p>
      ) : (
        <form className="form" onSubmit={onSubmit} noValidate>
          <div className="form-row">
            <label>Profile type</label>
            <div style={{ padding: '6px 0' }}>Series</div>
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

          <DownloadProfileForm form={form as any} mode={'series'} seasons={[]} />

          <div className="actions">
            <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting} />
          </div>
        </form>
      )}
    </section>
  )
}
