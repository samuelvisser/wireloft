import type {DownloadMode, FilenameRestrictionMode, ThumbnailMode} from '../../types/schemas/settings'
import ReadMore from '../../utils/ReadMore'
import CronEditor from './CronEditor'
import type {SettingsTabProps} from './SettingsTabTypes'
import {
    DurationField,
    NumberField,
    SelectField,
    SettingsDisclosure,
    SettingsSection,
    TextField,
    ToggleField,
} from './SettingsControls'

const FILENAME_RESTRICTION_MODES = ['unrestricted', 'windows', 'restricted'] as const
const FILENAME_RESTRICTION_LABELS = {
    unrestricted: 'Minimal restrictions',
    windows: 'Windows-compatible filenames',
    restricted: 'Restricted filenames',
} satisfies Record<FilenameRestrictionMode, string>

const DOWNLOAD_MODES = ['direct', 'temporary'] as const
const DOWNLOAD_MODE_LABELS = {
    direct: 'Save directly to downloads',
    temporary: 'Save to temporary folder first',
} satisfies Record<DownloadMode, string>

const THUMBNAIL_MODES = ['no_thumbnail', 'embed', 'sidecar', 'embed_and_sidecar'] as const
const THUMBNAIL_MODE_LABELS = {
    no_thumbnail: 'No thumbnail',
    embed: 'Embed in media',
    sidecar: 'Download besides media',
    embed_and_sidecar: 'Both embed and download',
} satisfies Record<ThumbnailMode, string>

function childPath(root: string, name: string) {
    const trimmedRoot = root.trim()
    if (!trimmedRoot) return ''
    const separator = trimmedRoot.includes('\\') && !trimmedRoot.includes('/') ? '\\' : '/'
    return `${trimmedRoot.replace(/[\\/]+$/, '')}${separator}${name}`
}

export default function DownloadsSettingsTab({
    draft,
    updateDraft,
    environmentVariableFor,
    errorFor,
    isFieldExplicit,
    isFieldDirty,
}: SettingsTabProps) {
    const temporaryDownloadRoot = (
        !isFieldExplicit('downloadSettings.temporaryDownloadRoot')
        && !isFieldDirty('downloadSettings.temporaryDownloadRoot')
    )
        ? childPath(draft.downloadSettings.downloadRoot, '.wireloft-temp')
        : draft.downloadSettings.temporaryDownloadRoot
    const rssCacheRoot = (
        !isFieldExplicit('downloadSettings.rssCacheRoot')
        && !isFieldDirty('downloadSettings.rssCacheRoot')
    )
        ? childPath(draft.downloadSettings.downloadRoot, '.wireloft-rss-cache')
        : draft.downloadSettings.rssCacheRoot

    return (
        <>
            <SettingsSection
                title="Storage and filenames"
                description="Where downloads are written and how filenames are made compatible with other systems."
            >
                <TextField
                    id="settings-download-root"
                    label="Download root"
                    value={draft.downloadSettings.downloadRoot}
                    error={errorFor('downloadSettings.downloadRoot')}
                    environmentVariable={environmentVariableFor('downloadSettings.downloadRoot')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.downloadRoot = value
                    })}
                    help="Local Media Profile output paths are resolved from this storage location where applicable."
                    wide
                />
                <TextField
                    id="settings-temporary-download-root"
                    label="Temporary download folder"
                    value={temporaryDownloadRoot}
                    error={errorFor('downloadSettings.temporaryDownloadRoot')}
                    environmentVariable={environmentVariableFor('downloadSettings.temporaryDownloadRoot')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.temporaryDownloadRoot = value
                    })}
                    help="Used whenever the system default or a Local Media Profile is set to save to a temporary folder first. Its default is .wireloft-temp inside the download root, but an explicit path can live elsewhere."
                    wide
                />
                <TextField
                    id="settings-rss-cache-root"
                    label="RSS cache folder"
                    value={rssCacheRoot}
                    error={errorFor('downloadSettings.rssCacheRoot')}
                    environmentVariable={environmentVariableFor('downloadSettings.rssCacheRoot')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.rssCacheRoot = value
                    })}
                    help={
                        <ReadMore summary="Stores media WireLoft prepares or caches while fulfilling RSS requests.">
                            <p>
                                By default, the cache lives in <code>.wireloft-rss-cache</code> inside the download root.
                            </p>
                            <p>
                                You may explicitly place it anywhere WireLoft can write, including container-local storage such as <code>/tmp/wireloft-rss-cache</code>. A container-local cache does not need a host volume, but is lost when the container is recreated.
                            </p>
                        </ReadMore>
                    }

                />
                <DurationField
                    id="settings-rss-cache-retention"
                    label="RSS cache retention period"
                    value={draft.downloadSettings.rssCacheRetentionSeconds}
                    backendUnit="seconds"
                    error={errorFor('downloadSettings.rssCacheRetentionSeconds')}
                    environmentVariable={environmentVariableFor('downloadSettings.rssCacheRetentionSeconds')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.rssCacheRetentionSeconds = value
                    })}
                    help="Cached RSS media expires after this much time without being served. Serving a cached MP4 refreshes its retention period."
                />
                <SelectField
                    id="settings-download-mode"
                    label="Default download behavior"
                    value={draft.downloadSettings.downloadMode}
                    options={DOWNLOAD_MODES}
                    optionLabels={DOWNLOAD_MODE_LABELS}
                    error={errorFor('downloadSettings.downloadMode')}
                    environmentVariable={environmentVariableFor('downloadSettings.downloadMode')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.downloadMode = value as DownloadMode
                    })}
                    help={
                        <ReadMore summary="Choose whether incomplete downloads are written in their destination or staged elsewhere first.">
                            <p>
                                <strong>Save directly to downloads</strong> writes temporary files next to the final media file and reserves the final filename while downloading.
                            </p>
                            <p>
                                <strong>Save to temporary folder first</strong> keeps all download and remux work in the temporary folder. Only after the media is complete does WireLoft choose an unused final filename and publish it to the destination.
                            </p>
                            <p>
                                The temporary folder may be on a different filesystem from the media library, including local storage while the library itself is on SMB, NFS, or another network mount. If a cross-filesystem copy is required, WireLoft copies the already-complete media to a hidden <code>.part</code> publication file on the destination filesystem and only then renames it to the final media filename.
                            </p>
                            <p>
                                Temporary mode is particularly useful when the destination folder is used by a media server and you do not want it to pick up partly downloaded or empty media files.
                            </p>
                        </ReadMore>
                    }
                />
                <SelectField
                    id="settings-thumbnail-mode"
                    label="Default thumbnail behavior"
                    value={draft.downloadSettings.thumbnailMode}
                    options={THUMBNAIL_MODES}
                    optionLabels={THUMBNAIL_MODE_LABELS}
                    error={errorFor('downloadSettings.thumbnailMode')}
                    environmentVariable={environmentVariableFor('downloadSettings.thumbnailMode')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.thumbnailMode = value as ThumbnailMode
                    })}
                    help={
                        <ReadMore summary="Choose how WireLoft stores the Daily Wire thumbnail for downloaded media.">
                            <p><strong>No thumbnail</strong> keeps downloads media-only.</p>
                            <p><strong>Embed in media</strong> stores the thumbnail as cover artwork inside the downloaded media file.</p>
                            <p><strong>Download besides media</strong> writes the image alongside the final media file, using the same basename.</p>
                            <p><strong>Both embed and download</strong> does both.</p>
                            <p>Local Media Profiles default to System and can override this setting individually.</p>
                        </ReadMore>
                    }
                />
                <SelectField
                    id="settings-filename-restriction-mode"
                    label="Filename restrictions"
                    value={draft.downloadSettings.filenameRestrictionMode}
                    options={FILENAME_RESTRICTION_MODES}
                    optionLabels={FILENAME_RESTRICTION_LABELS}
                    error={errorFor('downloadSettings.filenameRestrictionMode')}
                    environmentVariable={environmentVariableFor('downloadSettings.filenameRestrictionMode')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.filenameRestrictionMode = value as FilenameRestrictionMode
                    })}
                    help={
                        <ReadMore summary={<span>Choose filename restriction mode to ensure filesystem compatibility.</span>}>
                            <p>
                                <strong>Minimal restrictions</strong> preserves Unicode and ordinary punctuation while preventing path-breaking characters
                            </p>
                            <p>
                                <strong>Windows-compatible</strong> removes characters Windows does not allow in filenames, plus ensures reserved
                                filenames are not used. Most unicode characters are preserved.
                            </p>
                            <p>
                                <strong>Restricted</strong> uses ASCII-only names without spaces or ampersands.
                            </p>
                        </ReadMore>
                    }
                />
            </SettingsSection>

            <SettingsSection
                title="Download processing"
                description="Limits and retry behaviour for downloads started by WireLoft."
            >
                <NumberField
                    id="settings-download-concurrency"
                    label="Concurrent downloads"
                    value={draft.downloadSettings.maxConcurrentDownloads}
                    min={1}
                    error={errorFor('downloadSettings.maxConcurrentDownloads')}
                    environmentVariable={environmentVariableFor('downloadSettings.maxConcurrentDownloads')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.maxConcurrentDownloads = value
                    })}
                    help="Higher values finish queues faster but use more CPU, bandwidth and disk I/O."
                />
                <NumberField
                    id="settings-download-attempts"
                    label="Maximum attempts"
                    value={draft.downloadSettings.maxDownloadAttempts}
                    min={1}
                    error={errorFor('downloadSettings.maxDownloadAttempts')}
                    environmentVariable={environmentVariableFor('downloadSettings.maxDownloadAttempts')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.maxDownloadAttempts = value
                    })}
                    help="Maximum automatic attempts before a download is marked as failed."
                />
                <DurationField
                    id="settings-download-timeout"
                    label="Download timeout"
                    value={draft.downloadSettings.downloadTimeoutSeconds}
                    backendUnit="seconds"
                    error={errorFor('downloadSettings.downloadTimeoutSeconds')}
                    environmentVariable={environmentVariableFor('downloadSettings.downloadTimeoutSeconds')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.downloadTimeoutSeconds = value
                    })}
                    help="Stops a single download attempt that makes no useful progress for too long."
                />
            </SettingsSection>

            <SettingsSection
                title="Video output"
                description="Controls the optional FFmpeg remux step for downloaded video."
            >
                <ToggleField
                    id="settings-remux-mp4"
                    label="Remux downloaded video to MP4"
                    checked={draft.downloadSettings.remuxVideoToMp4}
                    environmentVariable={environmentVariableFor('downloadSettings.remuxVideoToMp4')}
                    onChange={(checked) => updateDraft((next) => {
                        next.downloadSettings.remuxVideoToMp4 = checked
                    })}
                    help="Repackages compatible video streams without re-encoding them."
                    wide
                />
                <TextField
                    id="settings-ffmpeg-path"
                    label="FFmpeg executable"
                    value={draft.downloadSettings.ffmpegPath}
                    error={errorFor('downloadSettings.ffmpegPath')}
                    environmentVariable={environmentVariableFor('downloadSettings.ffmpegPath')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.ffmpegPath = value
                    })}
                    help="Use ffmpeg when it is on PATH, or enter an absolute executable path."
                    wide
                />
            </SettingsSection>

            <SettingsDisclosure
                title="Verification and file watcher"
                description="Periodic integrity checks and detection of files changed outside WireLoft."
            >
                <CronEditor
                    id="settings-verify-downloads-cron"
                    label="Verify downloads schedule"
                    value={draft.downloadSettings.verifyDownloadsCron}
                    error={errorFor('downloadSettings.verifyDownloadsCron')}
                    environmentVariable={environmentVariableFor('downloadSettings.verifyDownloadsCron')}
                    onChange={(value) => updateDraft((next) => {
                        next.downloadSettings.verifyDownloadsCron = value
                    })}
                />
                <ToggleField
                    id="settings-file-watcher-enabled"
                    label="Enable file watcher"
                    checked={draft.fileWatcher.enabled}
                    environmentVariable={environmentVariableFor('fileWatcher.enabled')}
                    onChange={(checked) => updateDraft((next) => {
                        next.fileWatcher.enabled = checked
                    })}
                    help="Scans tracked downloads for files missing, renamed or otherwise changed outside WireLoft."
                />
                <CronEditor
                    id="settings-file-watcher-cron"
                    label="File watcher schedule"
                    value={draft.fileWatcher.scanCron}
                    error={errorFor('fileWatcher.scanCron')}
                    environmentVariable={environmentVariableFor('fileWatcher.scanCron')}
                    onChange={(value) => updateDraft((next) => {
                        next.fileWatcher.scanCron = value
                    })}
                />
                <ToggleField
                    id="settings-file-size-verification"
                    label="Verify file size"
                    checked={draft.fileWatcher.verifyFileSize}
                    environmentVariable={environmentVariableFor('fileWatcher.verifyFileSize')}
                    onChange={(checked) => updateDraft((next) => {
                        next.fileWatcher.verifyFileSize = checked
                    })}
                    help={
                        <ReadMore summary="Detects truncated or externally replaced files in addition to missing files.">
                            <p>
                                If this setting is enabled, WireLoft will consider a file whose size is either zero
                                or smaller than it was when it was first downloaded a corrupt file and treats it as such.
                            </p>
                        </ReadMore>
                    }
                />
            </SettingsDisclosure>
        </>
    )
}