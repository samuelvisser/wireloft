import MediaProfileForm, { type MediaProfileFormValue } from '../MediaProfileForm'

type MediaProfile = {
  id: number
  slug: string
  name: string
  outputTemplate: string
  preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only'
  downloadSeriesImages: boolean
}

type Props = {
  profiles: MediaProfile[] | null
  profilesError: string | null
  selectedProfileId: string | null
  setSelectedProfileId: (id: string | null) => void
  newProfile: MediaProfileFormValue
  setNewProfile: (v: MediaProfileFormValue) => void
  newProfileState: MediaProfileFormValue | null
  setNewProfileState: (v: MediaProfileFormValue | null) => void
  emptyProfile: MediaProfileFormValue
  canContinue: boolean
  onBack: () => void
  onContinue: () => void
  onCancel: () => void
  slug?: string
}

import DailywireShowCard from './DailywireShowCard'

export default function MediaProfileStep({
  profiles,
  profilesError,
  selectedProfileId,
  setSelectedProfileId,
  newProfile,
  setNewProfile,
  newProfileState,
  setNewProfileState,
  emptyProfile,
  canContinue,
  onBack,
  onContinue,
  onCancel,
  slug,
}: Props) {
  return (
    <div className="wizard-with-aside">
      <div className="wizard-main">
        <div className="form form-fluid">
          {/* Existing profiles list */}
          <div className="form-row">
            <label>Choose a media profile</label>
            <div className="card-grid" role="list">
              {profiles === null ? (
                <div role="listitem" className="card">Loading profiles...</div>
              ) : profiles.length === 0 ? (
                <div role="listitem" className="card">{profilesError ?? 'No profiles found'}</div>
              ) : (
                profiles.map((p) => {
                  const selected = selectedProfileId === p.slug
                  return (
                    <button
                      key={p.slug}
                      type="button"
                      role="listitem"
                      className={selected ? 'card selected' : 'card'}
                      aria-pressed={selected}
                      onClick={() => {
                        if (selected) {
                          // Deselect: restore previous form state (if any)
                          setSelectedProfileId(null)
                          setNewProfile(newProfileState ?? emptyProfile)
                          setNewProfileState(null)
                        } else {
                          // Selecting a profile
                          if (selectedProfileId === null) {
                            // Save current form before replacing it with the selected profile
                            setNewProfileState(newProfile)
                          }
                          setSelectedProfileId(p.slug)
                          setNewProfile({
                            name: p.name,
                            outputPathTemplate: p.outputTemplate,
                            preferredFormat: p.preferredFormat,
                            downloadSeriesImages: p.downloadSeriesImages,
                          })
                        }
                      }}
                    >
                      <div className="card-title">{p.name}</div>
                      <div className="card-sub">{p.outputTemplate}</div>
                      <div className="card-meta">
                        <span>{p.preferredFormat}</span>
                        <span>• {p.downloadSeriesImages ? 'Series images ✓' : 'Series images ✕'}</span>
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>

          {/* Divider and label under it */}
          <hr className="divider" aria-hidden="true" />
          <div className="divider-label" aria-hidden="true">{selectedProfileId ? 'Update current profile' : 'Or create a new profile'}</div>

          {/* New profile form */}
          <MediaProfileForm
            value={newProfile}
            onChange={(v) => {
              setNewProfile(v)
            }}
            autoFocusName
          />

          <div className="actions">
            <button type="button" className="btn" onClick={onBack}>
              Back
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={onContinue}
              disabled={!canContinue}
            >
              Continue
            </button>
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar with DailyWire show details */}
      {slug ? (
        <aside className="wizard-aside" aria-label="Selected show details">
          <DailywireShowCard slug={slug} />
        </aside>
      ) : null}
    </div>
  )
}
