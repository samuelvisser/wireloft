import { useMemo, useState } from 'react'
import MediaProfileForm, { MediaProfileFormValue } from './MediaProfileForm'

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

type MediaProfile = {
  id: string
  name: string
  outputPathTemplate: string
  preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only'
  downloadSeriesImages: boolean
}

type NewProfileForm = MediaProfileFormValue

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
  // Wizard step: 1 = URL, 2 = Media Profile, 3 = Show
  const [step, setStep] = useState<1 | 2 | 3>(1)

  // Step 1: URL
  const [rawUrl, setRawUrl] = useState('')
  const result = useMemo(() => validateShowUrl(rawUrl), [rawUrl])
  const urlValid = result.domainOk && result.pathOk && result.slugOk
  const showUrlErrors = rawUrl.trim().length > 0

  // Step 2: Media Profile
  const [profiles] = useState<MediaProfile[]>([
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
  ])
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null)
  const [newProfile, setNewProfile] = useState<NewProfileForm>({
    name: '',
    outputPathTemplate: '',
    preferredFormat: '1080p',
    downloadSeriesImages: true,
  })

  const creatingProfileValid =
    newProfile.name.trim().length > 0 && newProfile.outputPathTemplate.trim().length > 0
  const canContinueFromProfile = selectedProfileId !== null || creatingProfileValid

  // Step 3: Show (summary for now)

  function handleFinish() {
    const selection: MediaProfile | NewProfileForm | undefined =
      selectedProfileId
        ? profiles.find((p) => p.id === selectedProfileId)
        : creatingProfileValid
        ? newProfile
        : undefined

    const summary = {
      url: result.normalized ?? rawUrl,
      profile: selection ?? null,
    }
    alert('Add show request:\n' + JSON.stringify(summary, null, 2))
    onCancel()
  }

  return (
    <section className="view" aria-labelledby="add-show-title">
      <div className="view-header">
        <h1 id="add-show-title">Add show</h1>
      </div>

      {/* Simple step header */}
      <div className="help" aria-live="polite" style={{ marginBottom: 12 }}>
        Step {step} of 3: {step === 1 ? 'URL' : step === 2 ? 'Media Profile' : 'Show'}
      </div>

      {/* Step content */}
      {step === 1 && (
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
              onChange={(e) => setRawUrl(e.target.value)}
              aria-invalid={showUrlErrors && !urlValid}
              aria-describedby="url-help url-errors"
            />
            <div id="url-help" className="help">
              Must be on dailywire.com, include /show/, and a show name.
            </div>
            {showUrlErrors && result.errors.length > 0 && (
              <ul id="url-errors" className="error-list" role="alert">
                {result.errors.map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => urlValid && setStep(2)}
              disabled={!urlValid}
            >
              Continue
            </button>
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {step === 2 && (
        <div className="form">
          {/* Existing profiles list */}
          <div className="form-row">
            <label>Choose a media profile</label>
            <div className="card-grid" role="list">
              {profiles.map((p) => {
                const selected = selectedProfileId === p.id
                return (
                  <button
                    key={p.id}
                    type="button"
                    role="listitem"
                    className={selected ? 'card selected' : 'card'}
                    aria-pressed={selected}
                    onClick={() => setSelectedProfileId(selected ? null : p.id)}
                  >
                    <div className="card-title">{p.name}</div>
                    <div className="card-sub">{p.outputPathTemplate}</div>
                    <div className="card-meta">
                      <span>{p.preferredFormat}</span>
                      <span>• {p.downloadSeriesImages ? 'Series images ✓' : 'Series images ✕'}</span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Divider and label under it */}
          <hr className="divider" aria-hidden="true" />
          <div className="divider-label" aria-hidden="true">Or create a new profile</div>

          {/* New profile form */}
          <MediaProfileForm
            value={newProfile}
            onChange={(v) => {
              setSelectedProfileId(null)
              setNewProfile(v)
            }}
            autoFocusName
          />

          <div className="actions">
            <button type="button" className="btn" onClick={() => setStep(1)}>
              Back
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => canContinueFromProfile && setStep(3)}
              disabled={!canContinueFromProfile}
            >
              Continue
            </button>
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="form">
          <div className="form-row">
            <label>Show URL</label>
            <div className="help">{result.normalized ?? rawUrl}</div>
          </div>

          <div className="form-row">
            <label>Media Profile</label>
            {selectedProfileId ? (
              (() => {
                const p = profiles.find((x) => x.id === selectedProfileId)!
                return (
                  <div>
                    <div><strong>{p.name}</strong></div>
                    <div className="help">{p.outputPathTemplate}</div>
                    <div className="help">{p.preferredFormat} • {p.downloadSeriesImages ? 'Series images ✓' : 'Series images ✕'}</div>
                  </div>
                )
              })()
            ) : (
              <div>
                <div><strong>{newProfile.name || '(unnamed profile)'}</strong></div>
                <div className="help">{newProfile.outputPathTemplate || '(no path set)'}</div>
                <div className="help">{newProfile.preferredFormat} • {newProfile.downloadSeriesImages ? 'Series images ✓' : 'Series images ✕'}</div>
              </div>
            )}
          </div>

          <div className="actions">
            <button type="button" className="btn" onClick={() => setStep(2)}>
              Back
            </button>
            <button type="button" className="btn btn-primary" onClick={handleFinish}>
              Finish
            </button>
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
