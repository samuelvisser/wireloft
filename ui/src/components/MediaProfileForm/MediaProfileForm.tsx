
import Switch from 'react-switch'

export type MediaProfileFormValue = {
  name: string
  outputTemplate: string
  preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only'
  downloadSeriesImages: boolean
}

type Props = {
  value: MediaProfileFormValue
  onChange: (value: MediaProfileFormValue) => void
  autoFocusName?: boolean
  nameError?: string | null
  onNameBlur?: () => void
}

export default function MediaProfileForm({ value, onChange, autoFocusName, nameError, onNameBlur }: Props) {
  return (
    <>
      <div className="form-row">
        <label htmlFor="mp-name">Name</label>
        <input
          id="mp-name"
          className="input"
          type="text"
          placeholder="My 4k Profile"
          value={value.name}
          autoFocus={autoFocusName}
          onChange={(e) => onChange({ ...value, name: e.target.value })}
          onBlur={onNameBlur}
          aria-invalid={!!nameError}
          aria-describedby={nameError ? 'mp-name-error' : undefined}
        />
        {nameError && (
          <div id="mp-name-error" className="help" role="alert" aria-live="polite">
            {nameError}
          </div>
        )}
      </div>
      <div className="form-row">
        <label htmlFor="mp-path">Output path template</label>
        <input
          id="mp-path"
          className="input"
          type="text"
          placeholder="D:/Media/Shows/{show}/{season}"
          value={value.outputTemplate}
          onChange={(e) => onChange({ ...value, outputTemplate: e.target.value })}
        />
        <div className="help">Use placeholders like {`{show}`} and {`{season}`}.</div>
      </div>
      <div className="form-row">
        <label htmlFor="mp-format">Preferred format</label>
        <select
          id="mp-format"
          className="input"
          value={value.preferredFormat}
          onChange={(e) => {
            const v = e.target.value as MediaProfileFormValue['preferredFormat']
            onChange({ ...value, preferredFormat: v })
          }}
        >
          <option value="4k">4k</option>
          <option value="1080p">1080p</option>
          <option value="720p">720p</option>
          <option value="Audio Only">Audio Only</option>
        </select>
      </div>
      <div className="form-row" style={{ alignItems: 'center' }}>
        <label htmlFor="mp-images">Download series images</label>
        <Switch
          id="mp-images"
          checked={value.downloadSeriesImages}
          onChange={(checked) => onChange({ ...value, downloadSeriesImages: checked })}
          onColor="#0ea5e9"
          offColor="#d1d5db"
          uncheckedIcon={false}
          checkedIcon={false}
        />
      </div>
    </>
  )
}
