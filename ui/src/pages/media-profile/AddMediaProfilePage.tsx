import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import MediaProfileForm, { MediaProfileFormValue } from '../../components/MediaProfileForm'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

export default function AddMediaProfilePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [value, setValue] = useState<MediaProfileFormValue>({
    name: '',
    outputTemplate: '',
    preferredFormat: '1080p',
    downloadSeriesImages: true,
  })
  const setErrorRef = useRef<((name: any, error: any) => void) | null>(null)

  const valid = useMemo(() => {
    return value.name.trim().length > 0 && value.outputTemplate.trim().length > 0
  }, [value])

  const onCancel = useCallback(() => navigate('/profiles'), [navigate])
  const onCreate = useCallback(async () => {
    if (!valid) return
    const r = await fetch(`${(window as any).appConfig.API_URL}/media-profiles`, {
      method: 'POST',
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
        <MediaProfileForm
          mode="create"
          value={value}
          onChange={setValue}
          autoFocusName
          onRegisterSetError={(fn) => { setErrorRef.current = fn as any }}
        />
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
