import { useCallback, useEffect, useMemo, useState } from 'react'
import MediaProfileForm, { MediaProfileFormValue } from '../../components/MediaProfileForm'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

function slugify(text: string | null | undefined): string {
  if (!text) return ''
  const s = String(text).trim().toLowerCase()
  const out: string[] = []
  for (const ch of s) {
    if (/[a-z0-9\-_.]/.test(ch)) out.push(ch)
    else if (/\s|[\/\\]/.test(ch)) out.push('-')
  }
  let slug = out.join('')
  while (slug.includes('--')) slug = slug.replace(/--/g, '-')
  return slug.replace(/^-+|-+$/g, '')
}

export default function AddMediaProfilePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [value, setValue] = useState<MediaProfileFormValue>({
    name: '',
    outputTemplate: '',
    preferredFormat: '1080p',
    downloadSeriesImages: true,
  })
  const [nameError, setNameError] = useState<string | null>(null)

  const valid = useMemo(() => {
    return value.name.trim().length > 0 && value.outputTemplate.trim().length > 0
  }, [value])

  // Clear name error when user edits the name
  useEffect(() => {
    setNameError(null)
  }, [value.name])

  const checkNameUnique = useCallback(async () => {
    const slug = slugify(value.name)
    if (!slug) {
      setNameError(null)
      return
    }
    try {
      const r = await fetch(`${(window as any).appConfig.API_URL}/media-profiles/${slug}`)
      if (r.ok) {
        setNameError('A media profile with this name already exists')
      } else if (r.status === 404) {
        setNameError(null)
      } else {
        // Ignore other statuses silently to avoid noisy UX
        setNameError(null)
      }
    } catch (e) {
      // Network errors: do not block user; no error message
      setNameError(null)
    }
  }, [value.name])

  const onCancel = useCallback(() => navigate('/profiles'), [navigate])
  const onCreate = useCallback(async () => {
    if (!valid || !!nameError) return
    const r = await fetch(`${(window as any).appConfig.API_URL}/media-profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(value),
    })
    if (!r.ok) {
      if (r.status === 409) {
        setNameError('A media profile with this name already exists')
        return
      }
      const msg = `Failed to create media profile (HTTP ${r.status})`
      console.error(msg)
      alert(msg)
      return
    }
    await qc.invalidateQueries({ queryKey: ['mediaProfiles'] })
    navigate('/profiles')
  }, [navigate, qc, valid, value, nameError])

  return (
    <section className="view" aria-labelledby="add-media-profile-title">
      <div className="view-header">
        <h1 id="add-media-profile-title">Add media profile</h1>
      </div>

      <div className="form">
        <MediaProfileForm
          value={value}
          onChange={setValue}
          autoFocusName
          nameError={nameError}
          onNameBlur={checkNameUnique}
        />
        <div className="actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn btn-primary" disabled={!valid || !!nameError} onClick={onCreate}>
            Create profile
          </button>
        </div>
      </div>
    </section>
  )
}
