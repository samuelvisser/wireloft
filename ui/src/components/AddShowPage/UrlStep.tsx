type Props = {
  rawUrl: string
  onChangeRawUrl: (v: string) => void
  urlValid: boolean
  showUrlErrors: boolean
  errors: string[]
  onContinue: () => void
  onCancel: () => void
}

export default function UrlStep({ rawUrl, onChangeRawUrl, urlValid, showUrlErrors, errors, onContinue, onCancel }: Props) {
  return (
    <form className="form" onSubmit={(e) => e.preventDefault()} noValidate>
      <div className="form-row">
        <label htmlFor="show-url">Daily Wire show URL</label>
        <input
          id="show-url"
          className="input"
          type="url"
          inputMode="url"
          autoFocus
          placeholder="https://www.dailywire.com/show/the-ben-shapiro-show"
          value={rawUrl}
          onChange={(e) => onChangeRawUrl(e.target.value)}
          aria-invalid={showUrlErrors && !urlValid}
          aria-describedby="url-help url-errors"
        />
        <div id="url-help" className="help">
          Must be on dailywire.com, include /show/, and a show name.
        </div>
        {showUrlErrors && errors.length > 0 && (
          <ul id="url-errors" className="error-list" role="alert">
            {errors.map((msg, i) => (
              <li key={i}>{msg}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={onContinue}
          disabled={!urlValid}
        >
          Continue
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
