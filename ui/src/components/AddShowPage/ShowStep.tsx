import ShowForm, { type ShowFormValue } from '../ShowForm'
import type { MediaProfileFormValue } from '../MediaProfileForm'

type Props = {
  normalizedUrl?: string
  rawUrl: string
  newProfile: MediaProfileFormValue
  showForm: ShowFormValue
  setShowForm: (v: ShowFormValue) => void
  onBack: () => void
  onFinish: () => void
  onCancel: () => void
}

export default function ShowStep({ normalizedUrl, rawUrl, newProfile, showForm, setShowForm, onBack, onFinish, onCancel }: Props) {
  return (
    <div className="form">
      <div className="form-row">
        <label>Show URL</label>
        <div className="help">{normalizedUrl ?? rawUrl}</div>
      </div>

      <div className="form-row">
        <label>Media Profile</label>
        <div>
          <div><strong>{newProfile.name || '(unnamed profile)'}</strong></div>
          <div className="help">{newProfile.outputPathTemplate || '(no path set)'}</div>
          <div className="help">{newProfile.preferredFormat} • {newProfile.downloadSeriesImages ? 'Series images ✓' : 'Series images ✕'}</div>
        </div>
      </div>

      <ShowForm value={showForm} onChange={setShowForm} />

      <div className="actions">
        <button type="button" className="btn" onClick={onBack}>
          Back
        </button>
        <button type="button" className="btn btn-primary" onClick={onFinish}>
          Finish
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
