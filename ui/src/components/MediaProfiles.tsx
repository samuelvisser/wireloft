import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

export default function MediaProfiles() {
  const navigate = useNavigate()
  const onAdd = useCallback(() => navigate('/add-media-profile'), [navigate])

  type MediaProfileItem = {
    id: string
    name: string
    outputPathTemplate: string
    preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only'
    downloadSeriesImages: boolean
  }

  const profiles: MediaProfileItem[] = [
    {
      id: 'p1',
      name: 'Default 1080p',
      outputPathTemplate: 'D:/Media/Shows/{show}/{season}',
      preferredFormat: '1080p',
      downloadSeriesImages: true,
    },
    {
      id: 'p2',
      name: 'Mobile 720p',
      outputPathTemplate: 'E:/Mobile/Shows/{show}',
      preferredFormat: '720p',
      downloadSeriesImages: false,
    },
  ]

  return (
    <section className="view" aria-labelledby="profiles-title">
      <div className="view-header">
        <h1 id="profiles-title">Media Profiles</h1>
        <button className="btn btn-primary" onClick={onAdd}>Add media profile</button>
      </div>

      <div className="form-row">
        <div className="card-grid" role="list" aria-label="Existing media profiles">
          {profiles.map((p) => (
            <div key={p.id} className="card" role="listitem" aria-label={p.name}>
              <div className="card-title">{p.name}</div>
              <div className="card-sub">{p.outputPathTemplate}</div>
              <div className="card-meta">
                <span>{p.preferredFormat}</span>
                <span>• {p.downloadSeriesImages ? 'Series images ✓' : 'Series images ✕'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
