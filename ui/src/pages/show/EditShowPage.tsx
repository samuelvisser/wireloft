import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ShowForm, { ShowFormValue, defaultShowFormValue } from '../../components/ShowForm'
import CustomMetadataEditor from '../../components/CustomMetadataEditor/CustomMetadataEditor'
import { useQueryClient } from '@tanstack/react-query'
import {useShow} from '../../lib/queries'

type RouteParams = { id?: string }

type FormState = ShowFormValue & {
  url: string
  localMediaProfileId: string
}

export default function EditShowPage() {
  const { id } = useParams<RouteParams>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [metadataOpen, setMetadataOpen] = useState(false)
  const {data: show} = useShow(id)
  const initializedShowId = useRef<string | undefined>(undefined)

  const [form, setForm] = useState<FormState>(() => ({
    url: id ? `https://www.dailywire.com/show/${id}` : '',
    localMediaProfileId: 'p1',
    ...defaultShowFormValue,
  }))

  type LocalMediaProfileName = { id: string; name: string }
  const [profiles, setProfiles] = useState<LocalMediaProfileName[] | null>(null)
  const [profilesError, setProfilesError] = useState<string | null>(null)

  useEffect(() => {
    if (!id || !show || show.slug !== id || initializedShowId.current === id) return

    initializedShowId.current = id
    setForm((prev) => ({
      ...prev,
      url: show.sharingUrl,
      name: show.title,
      author: show.authorName,
    }))
  }, [id, show])

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${(window as any).appConfig.API_URL}/show-local-media-profiles`, { signal: controller.signal, credentials: 'include' })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()
        const items = (data as any[]).map((p) => ({ id: p.slug, name: p.name }))
        setProfiles(items)
        // Ensure selected value is valid
        setForm((prev) => {
          if (!prev.localMediaProfileId || !items.some((x) => x.id === prev.localMediaProfileId)) {
            return { ...prev, localMediaProfileId: items[0]?.id ?? '' }
          }
          return prev
        })
      })
      .catch((e: any) => {
        if (e.name !== 'AbortError') {
          console.error('Failed to load media profiles', e)
          setProfilesError('Failed to load media profiles')
          setProfiles([])
        }
      })
    return () => controller.abort()
  }, [])

  const onCancel = () => navigate(`/show/${id ?? ''}`)
  const onSave = async () => {
    if (!id || !show) return
    const payload = {
      title: form.name,
      description: show.description,
      sharingUrl: form.url,
      membershipLevel: show.membershipLevel,
      authorName: form.author,
      authorHeadshotPath: show.authorHeadshotPath ?? null,
      backgroundImagePath: show.backgroundImagePath ?? null,
      logoImagePath: show.logoImagePath ?? null,
      thumbnailLandscapePath: show.thumbnailLandscapePath ?? null,
      thumbnailPortraitPath: show.thumbnailPortraitPath ?? null,
      thumbnailSquarePath: show.thumbnailSquarePath ?? null,
    }
    const r = await fetch(`${(window as any).appConfig.API_URL}/shows/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    })
    if (!r.ok) {
      const msg = `Failed to save show (HTTP ${r.status})`
      console.error(msg)
      alert(msg)
      return
    }
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['show', id] }),
      qc.invalidateQueries({ queryKey: ['shows'] }),
      qc.invalidateQueries({ queryKey: ['showsView'] }),
    ])
    navigate(`/show/${id ?? ''}`)
  }

  if (!id) {
    return (
      <section className="view" aria-labelledby="edit-show-title">
        <div className="view-header">
          <h1 id="edit-show-title">Edit show</h1>
        </div>
        <p>Show not found.</p>
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="button" className="btn" onClick={() => navigate('/')}>Back</button>
        </div>
      </section>
    )
  }

  return (
    <section className="view" aria-labelledby="edit-show-title">
      <div className="view-header">
        <h1 id="edit-show-title">Edit show</h1>
        {show && (
          <button type="button" className="btn" onClick={() => setMetadataOpen(true)}>
            Metadata
          </button>
        )}
      </div>

      <form className="form" onSubmit={(e) => e.preventDefault()}>
        <div className="form-row">
          <label htmlFor="show-url">Show URL</label>
          <input
            id="show-url"
            className="input"
            type="url"
            inputMode="url"
            placeholder="https://www.dailywire.com/show/the-ben-shapiro-show"
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
            disabled
          />
        </div>

        <div className="form-row">
          <label htmlFor="media-profile">Media Profile</label>
          <select
            id="media-profile"
            className="input"
            value={form.localMediaProfileId}
            onChange={(e) => setForm({ ...form, localMediaProfileId: e.target.value })}
            disabled
          >
            {profiles === null ? (
              <option>Loading profiles...</option>
            ) : profiles.length === 0 ? (
              <option>{profilesError ?? 'No profiles found'}</option>
            ) : (
              profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))
            )}
          </select>
        </div>

        <ShowForm
          value={form}
          onChange={(v: ShowFormValue) => setForm((prev) => ({ ...prev, ...v }))}
        />

        <div className="actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={onSave} disabled={!show}>Save changes</button>
        </div>
      </form>

      <CustomMetadataEditor
        open={metadataOpen}
        title="Show metadata"
        scope="show"
        metadata={show?.customMetadata ?? {}}
        endpoint={`/shows/${encodeURIComponent(id)}/metadata`}
        invalidateQueryKeys={[
          ['show', id],
          ['shows'],
          ['showsView'],
        ]}
        onDismiss={() => setMetadataOpen(false)}
      />
    </section>
  )
}
