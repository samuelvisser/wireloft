import {useCallback, useEffect, useState} from 'react'
import {useNavigate} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import {useMediaProfiles} from '../lib/queries'
import {useQueryClient} from '@tanstack/react-query'
import {MediaProfileRead} from "../types/schemas/media_profile";
import {PreferredFormatReg} from "../types/media_profile";
import { toast } from 'react-hot-toast'

export default function MediaProfilesPage() {
    const navigate = useNavigate()
    const qc = useQueryClient()
    const onAdd = useCallback(() => navigate('/add-media-profile'), [navigate])
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

    const [confirmProfile, setConfirmProfile] = useState<MediaProfileRead | null>(null)
    const openConfirm = (p: MediaProfileRead) => setConfirmProfile(p)
    const closeConfirm = () => setConfirmProfile(null)
    const onConfirmDelete = async () => {
        if (!confirmProfile) return

        const r = await fetch(`${(window as any).appConfig.API_URL}/media-profiles/${confirmProfile.slug}`, { method: 'DELETE', credentials: 'include' })
        if (!r.ok) {
            // Try to parse server error in the documented format and show a toast error
            let friendly = `Failed to delete media profile (HTTP ${r.status})`
            try {
                const data = await r.json().catch(() => null as any)
                const details: any[] | undefined = data?.detail
                if (Array.isArray(details)) {
                    const allErr = details.find((d) => Array.isArray(d?.loc) && d.loc[0] === 'body' && d.loc[1] === '__all__')
                    if (allErr) {
                        if (allErr.type === 'integrity_error') {
                            friendly = 'This media profile is in use, it cannot be deleted'
                        } else if (typeof allErr.msg === 'string' && allErr.msg.trim()) {
                            friendly = allErr.msg
                        }
                    }
                }
            } catch (e) {
                // ignore JSON parse errors; keep friendly as generic
            }
            console.error(friendly)
            toast.error(friendly)
            setConfirmProfile(null)
            return
        }
        await qc.invalidateQueries({queryKey: ['mediaProfiles']})
        setConfirmProfile(null)
    }

    const {data: profiles, isLoading, error} = useMediaProfiles()

    return (
        <section className="view" aria-labelledby="profiles-title">
            <div className="view-header">
                <h1 id="profiles-title">Media Profiles</h1>
                <button className="btn btn-primary" onClick={onAdd}>Add media profile</button>
            </div>

            <div className="form-row">
                <div className="table-wrapper">
                    <table className="table" aria-label="Existing media profiles">
                        <thead>
                        <tr>
                            <th scope="col">Name</th>
                            <th scope="col">Output Path Template</th>
                            <th scope="col">Preferred Format</th>
                            <th scope="col">Series Images</th>
                            <th scope="col" style={{width: 100, textAlign: 'right'}}>Actions</th>
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
                            profiles.map((p: MediaProfileRead) => (
                                <tr
                                    key={p.id}
                                    aria-label={p.name}
                                    tabIndex={0}
                                    style={{cursor: 'pointer'}}
                                    onClick={() => navigate(`/edit-media-profile/${p.slug}`, {
                                        state: {
                                            ...p,
                                            outputPathTemplate: p.outputTemplate
                                        }
                                    })}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault()
                                            navigate(`/edit-media-profile/${p.slug}`, {
                                                state: {
                                                    ...p,
                                                    outputPathTemplate: p.outputTemplate
                                                }
                                            })
                                        }
                                    }}
                                >
                                    <td data-label="Name">{p.name}</td>
                                    <td data-label="Output Path Template"
                                        className="mono truncate">{p.outputTemplate}</td>
                                    <td data-label="Preferred Format">{PreferredFormatReg.getLabelLoose(p.preferredFormat)}</td>
                                    <td data-label="Series Images">{p.downloadSeriesImages ? '✓' : '✕'}</td>
                                    <td data-label="Actions" style={{textAlign: 'right'}}>
                                        <div style={{display: 'inline-flex', gap: 6, flexWrap: 'wrap'}}>
                                            {isMobile ? (
                                                <>
                                                    <button
                                                        type="button"
                                                        className="btn"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            navigate(`/edit-media-profile/${p.slug}`, {state: p})
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
                                                        aria-label={`Edit ${p.name}`}
                                                        title="Edit"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            navigate(`/edit-media-profile/${p.slug}`, {state: p})
                                                        }}
                                                    >
                                                        <FontAwesomeIcon icon={editIcon} />
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="icon-btn"
                                                        aria-label={`Delete ${p.name}`}
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
                            <h2 id="delete-title" className="modal-title">Delete media profile</h2>
                        </div>
                        <p id="delete-desc" className="modal-text">
                            Are you sure you want to delete "{confirmProfile.name}"? This action cannot be undone.
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
