import {useCallback, useMemo} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate} from 'react-router-dom'
import {useLocalMediaProfiles, usePodcastDownloadProfiles, useShows} from '../../lib/queries'
import DownloadProfileForm from '../../components/DownloadProfile/DownloadProfileForm'
import {PodcastDownloadProfileCreateIn, PodcastDownloadProfileCreateSchema} from '../../types/schemas/podcast_download_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'


type PodcastForm = PodcastDownloadProfileCreateIn

type ShowOption = { id: number; name: string }

export default function AddPodcastDownloadProfilePage() {
  const navigate = useNavigate()

  const { data: shows } = useShows()
  const { data: mediaProfiles } = useLocalMediaProfiles()

  const showOptions: ShowOption[] = useMemo(() => {
    const arr: ShowOption[] = []
    if (Array.isArray(shows)) {
      for (const s of shows as any[]) {
        const id = (s as any).id
        const name = (s as any).name ?? (s as any).slug ?? String(id)
        if (typeof id === 'number') arr.push({ id, name: String(name) })
      }
    }
    return arr
  }, [shows])

  const defaultValuesPodcast: PodcastForm = useMemo(() => ({
    showId: showOptions[0]?.id ?? 0,
    localMediaProfileId: (mediaProfiles?.[0] as LocalMediaProfileRead | undefined)?.id ?? 0,
    enableProfile: true,
    downloadWithCountdown: false,
    redownloadFinal: true,
    downloadDaysInPast: 180,
    deleteOlderEpisodes: true,
  }), [showOptions, mediaProfiles])

  const form = useForm<PodcastForm>({
    resolver: zodResolver(PodcastDownloadProfileCreateSchema),
    mode: 'onBlur',
    shouldFocusError: true,
    defaultValues: defaultValuesPodcast,
  })

  const onCancel = useCallback(() => navigate('/download-profiles'), [navigate])

  const { refetch: refetchPod } = usePodcastDownloadProfiles()

  const submitFn = async (data: PodcastForm) => {
    const base = (window as any).appConfig.API_URL
    const endpoint = 'podcast-download-profiles'
    return fetch(`${base}/${endpoint}` , {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    })
  }

  const onSuccess = async () => {
    await Promise.all([refetchPod()])
    navigate('/download-profiles')
  }

  const onSubmit = buildServerAwareSubmit(form as any, async (dataOut: PodcastForm) => {
    const res = await submitFn(dataOut)
    if (res?.ok) await onSuccess()
    return res
  })

  const { formState: { isSubmitting } } = form

  return (
    <section className="view" aria-labelledby="add-download-profile-title">
      <div className="view-header">
        <h1 id="add-download-profile-title">Add podcast download profile</h1>
      </div>

      <form className="form" onSubmit={onSubmit} noValidate>
        <div className="form-row">
          <label htmlFor="show-id">Show</label>
          <select
            id="show-id"
            className="input"
            value={String((form.watch('showId') as any) ?? '')}
            onChange={(e) => form.setValue('showId' as any, Number(e.target.value), { shouldDirty: true, shouldValidate: true })}
          >
            {showOptions.length === 0 ? (
              <option>No shows found</option>
            ) : (
              showOptions.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))
            )}
          </select>
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

        <DownloadProfileForm form={form as any} mode={'podcast'} />

        <div className="actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting} />
        </div>
      </form>
    </section>
  )
}
