import { useEffect, useState } from 'react'
import MediaProfileForm, { type MediaProfileFormValue } from '../MediaProfileForm'
import { useMediaProfiles } from '../../lib/queries'
import type { AddShowMediaProfileUpsert } from '../../types/addShow'

type MediaProfile = {
  id: number
  slug: string
  name: string
  outputTemplate: string
  preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only'
  downloadSeriesImages: boolean
}

type Props = {
  value: AddShowMediaProfileUpsert
  onChange: (v: AddShowMediaProfileUpsert) => void
  onBack: () => void
  onContinue: () => void
  onCancel: () => void
  slug?: string
}

import DailywireShowCard from './DailywireShowCard'

export default function MediaProfileStep({ value, onChange, onBack, onContinue, onCancel, slug }: Props) {
  const profilesQuery = useMediaProfiles()
  const profiles: MediaProfile[] | undefined = profilesQuery.data as any
  const profilesError = profilesQuery.isError ? ((profilesQuery.error as any)?.message ?? 'Failed to load media profiles') : null

  const defaultEmptyForm: MediaProfileFormValue = {
    name: '',
    outputPathTemplate: '',
    preferredFormat: '1080p',
    downloadSeriesImages: true,
  }

  const initialSelectedId = (value as any)?.op === 'update_by_slug' ? (value as any)?.slug ?? null : null
  const initialForm: MediaProfileFormValue = {
    name: (value as any)?.name ?? '',
    outputPathTemplate: (value as any)?.outputTemplate ?? '',
    preferredFormat: ((value as any)?.preferredFormat ?? '1080p') as MediaProfileFormValue['preferredFormat'],
    downloadSeriesImages: (value as any)?.downloadSeriesImages ?? true,
  }

  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(initialSelectedId)
  const [formValue, setFormValue] = useState<MediaProfileFormValue>(initialForm)
  const [formSnapshot, setFormSnapshot] = useState<MediaProfileFormValue | null>(null)

  // Keep parent in sync whenever selection or form changes
  useEffect(() => {
    const base = {
      name: formValue.name,
      outputTemplate: formValue.outputPathTemplate,
      preferredFormat: formValue.preferredFormat,
      downloadSeriesImages: formValue.downloadSeriesImages,
    }
    if (selectedProfileId) {
      onChange({ op: 'update_by_slug', slug: selectedProfileId, ...base })
    } else {
      onChange({ op: 'create_new', ...base })
    }
  }, [selectedProfileId, formValue])

  const canContinue = !!selectedProfileId || (formValue.name.trim().length > 0 && formValue.outputPathTemplate.trim().length > 0)

  return (
    <div className="wizard-with-aside">
      <div className="wizard-main">
        <div className="form form-fluid">
          {/* Existing profiles list */}
          <div className="form-row">
            <label>Choose a media profile</label>
            <div className="card-grid" role="list">
              {profilesQuery.isPending ? (
                <div role="listitem" className="card">Loading profiles...</div>
              ) : !profiles || profiles.length === 0 ? (
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
                          setFormValue(formSnapshot ?? defaultEmptyForm)
                          setFormSnapshot(null)
                        } else {
                          // Selecting a profile
                          if (selectedProfileId === null) {
                            // Save current form before replacing it with the selected profile
                            setFormSnapshot(formValue)
                          }
                          setSelectedProfileId(p.slug)
                          setFormValue({
                            name: p.name,
                            outputPathTemplate: p.outputTemplate,
                            preferredFormat: p.preferredFormat as any,
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
            value={formValue}
            onChange={(v) => {
              setFormValue(v)
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
