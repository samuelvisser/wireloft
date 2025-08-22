import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import MediaProfileForm, { MediaProfileFormValue } from './MediaProfileForm'

// Minimal local fallback data to support direct URL access without backend
const fallbackProfiles = [
  {
    id: 'p1',
    name: 'Default 1080p',
    outputPathTemplate: 'D:/Media/Shows/{show}/{season}',
    preferredFormat: '1080p' as const,
    downloadSeriesImages: true,
  },
  {
    id: 'p2',
    name: 'Mobile 720p',
    outputPathTemplate: 'E:/Mobile/Shows/{show}',
    preferredFormat: '720p' as const,
    downloadSeriesImages: false,
  },
]

type RouteParams = {
  id?: string
}

export default function EditMediaProfile() {
  const navigate = useNavigate()
  const { id } = useParams<RouteParams>()
  const location = useLocation() as { state?: any }

  const initialFromState = location.state as (MediaProfileFormValue & { id?: string }) | undefined

  const resolvedInitial: MediaProfileFormValue | undefined = useMemo(() => {
    if (initialFromState) {
      // Use values passed from the list
      const { name, outputPathTemplate, preferredFormat, downloadSeriesImages } = initialFromState
      return { name, outputPathTemplate, preferredFormat, downloadSeriesImages }
    }
    // Fallback: simple lookup from local array by id
    const found = fallbackProfiles.find((p) => p.id === id)
    if (found) {
      const { name, outputPathTemplate, preferredFormat, downloadSeriesImages } = found
      return { name, outputPathTemplate, preferredFormat, downloadSeriesImages }
    }
    return undefined
  }, [id, initialFromState])

  const [value, setValue] = useState<MediaProfileFormValue | undefined>(resolvedInitial)

  useEffect(() => {
    setValue(resolvedInitial)
  }, [resolvedInitial])

  const valid = useMemo(() => {
    if (!value) return false
    return value.name.trim().length > 0 && value.outputPathTemplate.trim().length > 0
  }, [value])

  const onCancel = useCallback(() => navigate('/profiles'), [navigate])
  const onSave = useCallback(() => {
    if (!value || !valid) return
    // Placeholder save: show what would be saved and go back
    alert('Save media profile changes:\n' + JSON.stringify({ id, ...value }, null, 2))
    navigate('/profiles')
  }, [id, navigate, valid, value])

  if (!value) {
    return (
      <section className="view" aria-labelledby="edit-media-profile-title">
        <div className="view-header">
          <h1 id="edit-media-profile-title">Edit media profile</h1>
        </div>
        <p>Profile not found.</p>
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="button" className="btn" onClick={onCancel}>Back</button>
        </div>
      </section>
    )
  }

  return (
    <section className="view" aria-labelledby="edit-media-profile-title">
      <div className="view-header">
        <h1 id="edit-media-profile-title">Edit media profile</h1>
      </div>

      <div className="form">
        <MediaProfileForm value={value} onChange={setValue} />
        <div className="actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn btn-primary" disabled={!valid} onClick={onSave}>
            Save changes
          </button>
        </div>
      </div>
    </section>
  )
}
