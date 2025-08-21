import React, { useMemo, useState } from 'react'

type AddShowProps = {
  onCancel: () => void
}

type ValidationResult = {
  domainOk: boolean
  pathOk: boolean
  slugOk: boolean
  errors: string[]
  normalized?: string
}

function ensureProtocol(input: string): string {
  let v = input.trim()
  if (!v) return v
  // If the string doesn't start with a URL scheme, prepend https://
  if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)) {
    v = 'https://' + v
  }
  return v
}

function validateShowUrl(input: string): ValidationResult {
  const withProto = ensureProtocol(input)

  try {
    const url = new URL(withProto)
    const host = url.hostname.toLowerCase()

    const domainOk = host === 'dailywire.com' || host === 'www.dailywire.com'
    const path = url.pathname

    const pathOk = path.startsWith('/show/')
    let slugOk = false
    if (pathOk) {
      const slug = path.slice('/show/'.length).split('/')[0]
      slugOk = !!slug
    }

    const errors: string[] = []
    if (!domainOk) errors.push('URL must be on dailywire.com')
    if (!pathOk) errors.push('URL must include /show/ in the path')
    if (!slugOk) errors.push('URL must include a show name after /show/ (e.g., the-ben-shapiro-show)')

    return { domainOk, pathOk, slugOk, errors, normalized: url.toString() }
  } catch {
    // If it's not parseable at all, surface all three rule errors
    return {
      domainOk: false,
      pathOk: false,
      slugOk: false,
      errors: [
        'URL must be on dailywire.com',
        'URL must include /show/ in the path',
        'URL must include a show name after /show/ (e.g., the-ben-shapiro-show)',
      ],
    }
  }
}

export default function AddShow({ onCancel }: AddShowProps) {
  const [rawUrl, setRawUrl] = useState('')

  const result = useMemo(() => validateShowUrl(rawUrl), [rawUrl])
  const allValid = result.domainOk && result.pathOk && result.slugOk

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!allValid) return
    // Placeholder action: navigate back for now; integration to persist will come later
    alert('Show URL looks valid!\n' + (result.normalized ?? ''))
    onCancel()
  }

  const showErrors = rawUrl.trim().length > 0

  return (
    <section className="view" aria-labelledby="add-show-title">
      <div className="view-header">
        <h1 id="add-show-title">Add show</h1>
      </div>

      <form className="form" onSubmit={onSubmit} noValidate>
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
            onChange={(e) => setRawUrl(e.target.value)}
            aria-invalid={showErrors && !allValid}
            aria-describedby="url-help url-errors"
          />
          <div id="url-help" className="help">
            Must be on dailywire.com, include /show/, and a show name.
          </div>
          {showErrors && result.errors.length > 0 && (
            <ul id="url-errors" className="error-list" role="alert">
              {result.errors.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="actions">
          <button type="submit" className="btn btn-primary" disabled={!allValid}>
            Continue
          </button>
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
