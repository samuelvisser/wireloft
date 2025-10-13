import {useCallback, useEffect, useMemo, useState} from 'react'
import {useNavigate} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import {useDownloadProfilesView} from '../lib/queries'
import {useQueryClient} from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { DownloadProfileReadView } from '../types/schemas/download_profile_view'
import { PreferredFormatReg } from '../types/local_media_profile'



export default function DownloadProfilesPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const onAdd = useCallback(() => navigate('/add-download-profile'), [navigate])
  const editIcon: IconProp = ['fas', 'pen-to-square']
  const deleteIcon: IconProp = ['fas', 'trash']

  // Track if we are on a small screen to render real text buttons on mobile
  const [isMobile, setIsMobile] = useState<boolean>(typeof window !== 'undefined' ? window.innerWidth <= 640 : false)
  useEffect(() => {
    if (typeof window === 'undefined') return
    const onResize = () => setIsMobile(window.innerWidth <= 640)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const { data: profilesRaw, isLoading, error } = useDownloadProfilesView()

  const profiles: DownloadProfileReadView[] | undefined = useMemo(() => {
    if (!profilesRaw) return undefined
    const arr = Array.isArray(profilesRaw) ? [...profilesRaw] : []
    // Ensure sort by show title
    arr.sort((a, b) => a.showTitle.localeCompare(b.showTitle, undefined, { sensitivity: 'base' }))
    return arr
  }, [profilesRaw])

  const [confirmProfile, setConfirmProfile] = useState<DownloadProfileReadView | null>(null)
  const openConfirm = (p: DownloadProfileReadView) => setConfirmProfile(p)
  const closeConfirm = () => setConfirmProfile(null)
  const onConfirmDelete = async () => {
    if (!confirmProfile) return

    const base = (window as any).appConfig.API_URL
    const endpoint = confirmProfile.type === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'
    const r = await fetch(`${base}/${endpoint}/${confirmProfile.id}`, { method: 'DELETE', credentials: 'include' })
    if (!r.ok) {
      let friendly = `Failed to delete download profile (HTTP ${r.status})`
      try {
        const data = await r.json().catch(() => null as any)
        const details: any[] | undefined = (data as any)?.detail
        if (Array.isArray(details)) {
          const allErr = details.find((d) => Array.isArray(d?.loc) && d.loc[0] === 'body' && d.loc[1] === '__all__')
          if (allErr) {
            if (allErr.type === 'integrity_error') {
              friendly = 'This download profile is in use, it cannot be deleted'
            } else if (typeof allErr.msg === 'string' && allErr.msg.trim()) {
              friendly = allErr.msg
            }
          }
        }
      } catch (_) {}
      console.error(friendly)
      toast.error(friendly)
      setConfirmProfile(null)
      return
    }

    await Promise.all([
      qc.invalidateQueries({ queryKey: ['downloadProfilesView'] }),
      qc.invalidateQueries({ queryKey: ['podcastDownloadProfiles'] }),
      qc.invalidateQueries({ queryKey: ['seriesDownloadProfiles'] }),
    ])
    setConfirmProfile(null)
  }

  return (
    <section className="view" aria-labelledby="profiles-title">
      <div className="view-header">
        <h1 id="profiles-title">Download Profiles</h1>
        <button className="btn btn-primary" onClick={onAdd}>Add download profile</button>
      </div>

      <div className="form-row">
        <div className="table-wrapper">
          <table className="table" aria-label="Existing download profiles">
            <thead>
              <tr>
                <th scope="col">Show Title</th>
                <th scope="col">Preferred Format</th>
                <th scope="col">Type</th>
                <th scope="col">Enabled</th>
                <th scope="col" style={{ width: 100, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !profiles ? (
                <tr>
                  <td colSpan={5}>Loading profiles...</td>
                </tr>
              ) : !profiles || profiles.length === 0 ? (
                <tr>
                  <td colSpan={5}>{(error as any)?.message ?? 'No profiles found'}</td>
                </tr>
              ) : (
                profiles.map((p: DownloadProfileReadView) => (
                  <tr
                    key={`${p.type}-${p.id}`}
                    aria-label={`${p.type} ${p.showTitle}`}
                    tabIndex={0}
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/edit-download-profile/${p.type}/${p.id}`, { state: p })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        navigate(`/edit-download-profile/${p.type}/${p.id}`, { state: p })
                      }
                    }}
                  >
                    <td data-label="Show Title">{p.showTitle}</td>
                    <td data-label="Preferred Format">{PreferredFormatReg.getLabelLoose(p.localMediaProfilePreferredFormat)}</td>
                    <td data-label="Type">{p.type}</td>
                    <td data-label="Enabled">{p.enableProfile ? '✓' : '✕'}</td>
                    <td data-label="Actions" style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
                        {isMobile ? (
                          <>
                            <button
                              type="button"
                              className="btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/edit-download-profile/${p.type}/${p.id}`, { state: p })
                              }}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn btn-danger"
                              onClick={(e) => {
                                e.stopPropagation();
                                openConfirm(p)
                              }}
                            >
                              Delete
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="icon-btn"
                              aria-label={`Edit ${p.type} ${p.showTitle}`}
                              title="Edit"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/edit-download-profile/${p.type}/${p.id}`, { state: p })
                              }}
                            >
                              <FontAwesomeIcon icon={editIcon} />
                            </button>
                            <button
                              type="button"
                              className="icon-btn"
                              aria-label={`Delete ${p.type} ${p.showTitle}` }
                              title="Delete"
                              onClick={(e) => {
                                e.stopPropagation();
                                openConfirm(p)
                              }}
                            >
                              <FontAwesomeIcon icon={deleteIcon} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {confirmProfile && (
        <div className="modal-overlay" role="presentation" onClick={closeConfirm}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            aria-describedby="delete-desc"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="modal-icon danger" aria-hidden>
                <FontAwesomeIcon icon={['fas', 'trash']} />
              </div>
              <h2 id="delete-title" className="modal-title">Delete download profile</h2>
            </div>
            <p id="delete-desc" className="modal-text">
              Are you sure you want to delete the download profile for "{confirmProfile.showTitle}"? This action cannot be undone.
            </p>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={closeConfirm}>Cancel</button>
              <button type="button" className="btn btn-danger" onClick={onConfirmDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
