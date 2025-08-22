import { useCallback, useMemo, useState } from 'react'
import MediaProfileForm, { MediaProfileFormValue } from '../../components/MediaProfileForm'
import { useNavigate } from 'react-router-dom'

export default function AddMediaProfilePage() {
  const navigate = useNavigate()
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
  const onCreate = useCallback(() => {
    if (!valid) return
    // Placeholder create: surface values and navigate back
    alert('Create media profile:\n' + JSON.stringify(value, null, 2))
    navigate('/profiles')
  }, [navigate, value, valid])

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
