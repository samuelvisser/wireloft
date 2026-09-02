import type {FilenameRestrictionMode} from '../../types/schemas/settings'
import ReadMore from '../../utils/ReadMore'
import CronEditor from './CronEditor'
import type {SettingsTabProps} from './SettingsTabTypes'
import {
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

export default function DownloadsSettingsTab({draft, updateDraft, environmentVariableFor, errorFor}: SettingsTabProps) {
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
                <SelectField
                    id="settings-filename-restriction-mode"
                    label="Filename restrictions"
                    value={draft.downloadSettings.filenameRestrictionMode}
                    options={FILENAME_RESTRICTION_MODES}
                    optionLabels={FILENAME_RESTRICTION_LABELS}
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
                <NumberField
                    id="settings-download-timeout"
                    label="Download timeout"
                    value={draft.downloadSettings.downloadTimeoutSeconds}
                    min={1}
                    unit="seconds"
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
                    help="Scans tracked download paths for files moved, removed or otherwise changed outside WireLoft."
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
                    help="Detects truncated or externally replaced files in addition to missing files."
                />
            </SettingsDisclosure>
        </>
    )
}
