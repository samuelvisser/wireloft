import {Controller, UseFormReturn} from 'react-hook-form'

import {useSettings} from '../../lib/settings'
import ReadMore from '../../utils/ReadMore'

const THUMBNAIL_MODE_LABELS = {
    no_thumbnail: 'No thumbnail',
    embed: 'Embed in media',
    sidecar: 'Download besides media',
    embed_and_sidecar: 'Both embed and download',
} as const

const METADATA_MODE_LABELS = {
    no_metadata: 'No metadata',
    embed: 'Embed in media',
    nfo: 'Download as NFO',
    embed_and_nfo: 'Both embed and download',
} as const

export default function LocalMediaProfileCommonFields({form}: { form: UseFormReturn<any> }) {
    const {control, register, formState: {errors}} = form
    const {data: settings} = useSettings()
    const systemDownloadModeLabel = !settings
        ? 'Loading system setting…'
        : settings.values.downloadSettings.downloadMode === 'temporary'
            ? 'Save to temporary folder first'
            : 'Save directly to downloads'
    const systemThumbnailModeLabel = !settings
        ? 'Loading system setting…'
        : THUMBNAIL_MODE_LABELS[settings.values.downloadSettings.thumbnailMode]
    const systemMetadataModeLabel = !settings
        ? 'Loading system setting…'
        : METADATA_MODE_LABELS[settings.values.downloadSettings.metadataMode]

    return (
        <>
            {errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

            {/* Hidden fields for id and slug to include them in submit when present */}
            <input type="hidden" {...register('id', {setValueAs: (v) => (v === '' || v == null ? undefined : Number(v))})} />
            <input type="hidden" {...register('slug')} />
            <input type="hidden" {...register('type')} />

            <div className="form-row">
                <label htmlFor="mp-name">Name</label>
                <input
                    id="mp-name"
                    className="input"
                    type="text"
                    placeholder="My 4k Profile"
                    {...register('name')}
                    aria-invalid={!!errors.name}
                    aria-describedby={errors.name ? 'mp-name-validate' : undefined}
                />
                {errors.name && (
                    <div id="mp-name-validate" className="error" role="alert" aria-live="polite">
                        {String(errors.name.message)}
                    </div>
                )}
            </div>

            <div className="form-row">
                <label htmlFor="local-media-download-mode">Download behavior</label>
                <Controller
                    control={control}
                    name="downloadMode"
                    render={({field}) => (
                        <select
                            id="local-media-download-mode"
                            className="input"
                            value={field.value ?? 'system'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.downloadMode}
                            aria-describedby={errors.downloadMode ? 'local-media-download-mode-errors' : 'local-media-download-mode-help'}
                        >
                            <option value="system">System ({systemDownloadModeLabel})</option>
                            <option value="direct">Save directly to downloads</option>
                            <option value="temporary">Save to temporary folder first</option>
                        </select>
                    )}
                />
                {errors.downloadMode && (
                    <div id="local-media-download-mode-errors" className="error" role="alert" aria-live="polite">
                        {errors.downloadMode.message as string}
                    </div>
                )}
                <div className="help" id="local-media-download-mode-help">
                    <ReadMore summary="Choose whether incomplete downloads are written in their destination or staged elsewhere first.">
                        <p>
                            <strong>System</strong> follows the current system-wide default.
                        </p>
                        <p>
                            <strong>Save directly to downloads</strong> writes download temporary files beside the final media destination and reserves the final filename while downloading.
                        </p>
                        <p>
                            <strong>Save to temporary folder first</strong> keeps download and processing files in the configured temporary folder and only publishes the completed media file at the end.
                        </p>
                        <p>
                            Temporary mode is particularly useful when the destination is watched by a media server and you do not want it to pick up partly downloaded or empty media files.
                            Save directly to downloads, due to its simple nature, is a little faster and less prone to errors. Though if errors do happen in either mode, WireLoft will
                            automatically restore from them.
                        </p>
                    </ReadMore>
                </div>
            </div>

            <div className="form-row">
                <label htmlFor="local-media-thumbnail-mode">Episode thumbnail behavior</label>
                <Controller
                    control={control}
                    name="thumbnailMode"
                    render={({field}) => (
                        <select
                            id="local-media-thumbnail-mode"
                            className="input"
                            value={field.value ?? 'system'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.thumbnailMode}
                            aria-describedby={errors.thumbnailMode ? 'local-media-thumbnail-mode-errors' : 'local-media-thumbnail-mode-help'}
                        >
                            <option value="system">System ({systemThumbnailModeLabel})</option>
                            <option value="no_thumbnail">No thumbnail</option>
                            <option value="embed">Embed in media</option>
                            <option value="sidecar">Download besides media</option>
                            <option value="embed_and_sidecar">Both embed and download</option>
                        </select>
                    )}
                />
                {errors.thumbnailMode && (
                    <div id="local-media-thumbnail-mode-errors" className="error" role="alert" aria-live="polite">
                        {errors.thumbnailMode.message as string}
                    </div>
                )}
                <div className="help" id="local-media-thumbnail-mode-help">
                    <ReadMore summary="Choose how this profile stores the Daily Wire thumbnail for downloaded media.">
                        <p><strong>System</strong> follows the current system-wide default.</p>
                        <p><strong>No thumbnail</strong> keeps downloads media-only.</p>
                        <p><strong>Embed in media</strong> stores the thumbnail as cover artwork inside the downloaded media file.</p>
                        <p><strong>Download besides media</strong> saves the thumbnail as an image alongside the media file.</p>
                        <p><strong>Both embed and download</strong> does both.</p>
                    </ReadMore>
                </div>
            </div>

            <div className="form-row">
                <label htmlFor="local-media-metadata-mode">Media metadata behavior</label>
                <Controller
                    control={control}
                    name="metadataMode"
                    render={({field}) => (
                        <select
                            id="local-media-metadata-mode"
                            className="input"
                            value={field.value ?? 'system'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.metadataMode}
                            aria-describedby={errors.metadataMode ? 'local-media-metadata-mode-errors' : 'local-media-metadata-mode-help'}
                        >
                            <option value="system">System ({systemMetadataModeLabel})</option>
                            <option value="no_metadata">No metadata</option>
                            <option value="embed">Embed in media</option>
                            <option value="nfo">Download as NFO</option>
                            <option value="embed_and_nfo">Both embed and download</option>
                        </select>
                    )}
                />
                {errors.metadataMode && (
                    <div id="local-media-metadata-mode-errors" className="error" role="alert" aria-live="polite">
                        {String(errors.metadataMode.message)}
                    </div>
                )}
                <div className="help" id="local-media-metadata-mode-help">
                    <ReadMore summary="Choose how this profile stores metadata for downloaded media.">
                        <p><strong>System</strong> follows the current system-wide default.</p>
                        <p><strong>No metadata</strong> leaves the downloaded media without WireLoft-generated metadata.</p>
                        <p><strong>Embed in media</strong> writes useful media-server metadata directly into supported media containers.</p>
                        <p><strong>Download as NFO</strong> writes the same metadata in a same-basename NFO file beside the media.</p>
                        <p><strong>Both embed and download</strong> does both.</p>
                        <p>HLS bundles cannot contain embedded file metadata, so only the NFO part applies when selected.</p>
                    </ReadMore>
                </div>
            </div>
        </>
    )
}
