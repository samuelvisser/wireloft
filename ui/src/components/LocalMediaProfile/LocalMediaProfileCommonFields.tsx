import {Controller, UseFormReturn} from 'react-hook-form'

import {useSettings} from '../../lib/settings'
import ReadMore from '../../utils/ReadMore'
import {createSelectRegistry} from '../../utils/selectRegistry'
import SimpleSelect from '../common/SimpleSelect'

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

const SUBTITLE_MODE_LABELS = {
    no_subtitles: 'No subtitles',
    embed: 'Embed in media',
    sidecar: 'Download besides media',
    embed_and_sidecar: 'Both embed and download',
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

    const systemSubtitleModeLabel = !settings
        ? 'Loading system setting…'
        : SUBTITLE_MODE_LABELS[settings.values.downloadSettings.subtitleMode]

    const downloadModeReg = createSelectRegistry('LocalMediaProfileDownloadMode', {
        system: {label: `System (${systemDownloadModeLabel})`},
        direct: {label: 'Save directly to downloads'},
        temporary: {label: 'Save to temporary folder first'},
    })
    const thumbnailModeReg = createSelectRegistry('LocalMediaProfileThumbnailMode', {
        system: {label: `System (${systemThumbnailModeLabel})`},
        no_thumbnail: {label: 'No thumbnail'},
        embed: {label: 'Embed in media'},
        sidecar: {label: 'Download besides media'},
        embed_and_sidecar: {label: 'Both embed and download'},
    })
    const metadataModeReg = createSelectRegistry('LocalMediaProfileMetadataMode', {
        system: {label: `System (${systemMetadataModeLabel})`},
        no_metadata: {label: 'No metadata'},
        embed: {label: 'Embed in media'},
        nfo: {label: 'Download as NFO'},
        embed_and_nfo: {label: 'Both embed and download'},
    })

    const subtitleModeReg = createSelectRegistry('LocalMediaProfileSubtitleMode', {
        system: {label: `System (${systemSubtitleModeLabel})`},
        no_subtitles: {label: 'No subtitles'},
        embed: {label: 'Embed in media'},
        sidecar: {label: 'Download besides media'},
        embed_and_sidecar: {label: 'Both embed and download'},
    })

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
                        <SimpleSelect
                            inputId="local-media-download-mode"
                            registry={downloadModeReg}
                            value={field.value ?? 'system'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.downloadMode}
                            aria-describedby={errors.downloadMode ? 'local-media-download-mode-errors' : 'local-media-download-mode-help'}
                        />
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
                        <SimpleSelect
                            inputId="local-media-thumbnail-mode"
                            registry={thumbnailModeReg}
                            value={field.value ?? 'system'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.thumbnailMode}
                            aria-describedby={errors.thumbnailMode ? 'local-media-thumbnail-mode-errors' : 'local-media-thumbnail-mode-help'}
                        />
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
                        <SimpleSelect
                            inputId="local-media-metadata-mode"
                            registry={metadataModeReg}
                            value={field.value ?? 'system'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.metadataMode}
                            aria-describedby={errors.metadataMode ? 'local-media-metadata-mode-errors' : 'local-media-metadata-mode-help'}
                        />
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

            <div className="form-row">
                <label htmlFor="local-media-subtitle-mode">Subtitle behavior</label>
                <Controller
                    control={control}
                    name="subtitleMode"
                    render={({field}) => (
                        <SimpleSelect
                            inputId="local-media-subtitle-mode"
                            registry={subtitleModeReg}
                            value={field.value ?? 'no_subtitles'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.subtitleMode}
                            aria-describedby={errors.subtitleMode ? 'local-media-subtitle-mode-errors' : 'local-media-subtitle-mode-help'}
                        />
                    )}
                />
                {errors.subtitleMode && (
                    <div id="local-media-subtitle-mode-errors" className="error" role="alert" aria-live="polite">
                        {String(errors.subtitleMode.message)}
                    </div>
                )}
                <div className="help" id="local-media-subtitle-mode-help">
                    <ReadMore summary="Choose how subtitles provided by The Daily Wire are stored with this media.">
                        <p><strong>No subtitles</strong> skips subtitle acquisition.</p>
                        <p><strong>Embed in media</strong> adds available subtitles as selectable tracks in supported containers.</p>
                        <p><strong>Download besides media</strong> saves language-specific SRT files, such as <code>Movie.en.srt</code>, beside the downloaded media for Plex and other media servers.</p>
                        <p><strong>Both embed and download</strong> does both.</p>
                        <p><strong>System</strong> follows the system-wide default. New movie profiles default to sidecars, and show profiles to no subtitles.</p>
                        <p>Embedding requires a supported media container, not a raw HLS bundle.</p>
                    </ReadMore>
                </div>
            </div>
        </>
    )
}
