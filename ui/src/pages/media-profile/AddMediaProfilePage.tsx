import { useCallback, useMemo, useState } from 'react'
import MediaProfileForm, { MediaProfileFormValue } from '../../components/MediaProfileForm'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

const API_BASE = 'http://localhost:5000/api'

export default function AddMediaProfilePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [value, setValue] = useState<MediaProfileFormValue>({
    name: '',
    outputPathTemplate: '',
    preferredFormat: '1080p',
    downloadSeriesImages: true,
  })

  const valid = useMemo(() => {
    return value.name.trim().length > 0 && value.outputPathTemplate.trim().length > 0
  }, [value])

  const onCancel = useCallback(() => navigate('/profiles'), [navigate])
  const onCreate = useCallback(async () => {
    if (!valid) return
    const r = await fetch(`${API_BASE}/media-profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(value),
    })
    if (!r.ok) {
      const msg = `Failed to create media profile (HTTP ${r.status})`
      console.error(msg)
      alert(msg)
      return
    }
    await qc.invalidateQueries({ queryKey: ['mediaProfiles'] })
    navigate('/profiles')
  }, [navigate, qc, valid, value])

  return (
    <section className="view" aria-labelledby="add-media-profile-title">
      <div className="view-header">
        <h1 id="add-media-profile-title">Add media profile</h1>
      </div>

      <div className="form">
        <MediaProfileForm value={value} onChange={setValue} autoFocusName />
        <div className="actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn btn-primary" disabled={!valid} onClick={onCreate}>
            Create profile
          </button>
        </div>
      </div>
    </section>
  )
}
