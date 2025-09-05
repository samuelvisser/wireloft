import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import MediaProfileForm, { MediaProfileFormValue } from '../../components/MediaProfileForm'
import { useQueryClient } from '@tanstack/react-query'

const API_BASE = 'http://localhost:5000/api'

type RouteParams = {
  id?: string
}

export default function EditMediaProfilePage() {
  const navigate = useNavigate()
  const { id } = useParams<RouteParams>()
  const location = useLocation() as { state?: any }
  const qc = useQueryClient()

  const initialFromState = location.state as (MediaProfileFormValue & { id?: string }) | undefined

  const resolvedInitial: MediaProfileFormValue | undefined = useMemo(() => {
    if (initialFromState) {
      // Use values passed from the list
      const { name, outputPathTemplate, preferredFormat, downloadSeriesImages } = initialFromState
      return { name, outputPathTemplate, preferredFormat, downloadSeriesImages }
    }
    return undefined
  }, [initialFromState])

  const [value, setValue] = useState<MediaProfileFormValue | undefined>(resolvedInitial)

  useEffect(() => {
    setValue(resolvedInitial)
  }, [resolvedInitial])

  const valid = useMemo(() => {
    if (!value) return false
    return value.name.trim().length > 0 && value.outputPathTemplate.trim().length > 0
  }, [value])

  const onCancel = useCallback(() => navigate('/profiles'), [navigate])
  const onSave = useCallback(async () => {
    if (!value || !valid || !id) return
    const r = await fetch(`${API_BASE}/media-profiles/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(value),
    })
    if (!r.ok) {
      const msg = `Failed to save media profile (HTTP ${r.status})`
      console.error(msg)
      alert(msg)
      return
    }
    await qc.invalidateQueries({ queryKey: ['mediaProfiles'] })
    navigate('/profiles')
  }, [id, navigate, qc, valid, value])

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
