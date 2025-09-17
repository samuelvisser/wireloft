import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import MediaProfileForm, { MediaProfileFormValue } from '../../components/MediaProfileForm'
import { useQueryClient } from '@tanstack/react-query'

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
      const { name, outputTemplate, preferredFormat, downloadSeriesImages } = initialFromState
      return { name, outputTemplate: outputTemplate, preferredFormat, downloadSeriesImages }
    }
    return undefined
  }, [initialFromState])

  const [value, setValue] = useState<MediaProfileFormValue | undefined>(resolvedInitial)
  const setErrorRef = useRef<((name: any, error: any) => void) | null>(null)

  useEffect(() => {
    setValue(resolvedInitial)
  }, [resolvedInitial])

  const valid = useMemo(() => {
    if (!value) return false
    return value.name.trim().length > 0 && value.outputTemplate.trim().length > 0
  }, [value])

  const onCancel = useCallback(() => navigate('/profiles'), [navigate])
  const onSave = useCallback(async () => {
    if (!value || !valid || !id) return
    const r = await fetch(`${(window as any).appConfig.API_URL}/media-profiles/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(value),
    })
    if (!r.ok) {
      if (r.status === 422) {
        try {
          const data = await r.json()
          const details = Array.isArray(data?.detail) ? data.detail : []
          for (const err of details) {
            const field = err?.loc?.[1]
            const msg = err?.msg ?? 'Invalid value'
            if (field && setErrorRef.current) {
              setErrorRef.current(field, { type: 'server', message: msg })
            }
          }
        } catch (_) {
          // ignore JSON parse errors
        }
        return
      }
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
        <MediaProfileForm mode="update" value={value} onChange={setValue} onRegisterSetError={(fn) => { setErrorRef.current = fn as any }} />
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
