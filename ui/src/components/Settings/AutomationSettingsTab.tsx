import type {SettingsTabProps} from './SettingsTabTypes'
import CronEditor from './CronEditor'
import {
    DurationField,
    NumberField,
    SettingsDisclosure,
    SettingsSection,
    TextField,
    ToggleField,
} from './SettingsControls'
import ReadMore from "../../utils/ReadMore";
import {formatDurationMinutes} from "../../utils/formatting";

export default function AutomationSettingsTab({draft, updateDraft, environmentVariableFor, errorFor}: SettingsTabProps) {

    return (
        <>
            <SettingsSection
                title="Scheduler"
                description="Global execution and retry settings for WireLoft background work."
            >
                <ToggleField
                    id="settings-scheduler-enabled"
                    label="Enable background scheduler"
                    checked={draft.scheduler.enabled}
                    environmentVariable={environmentVariableFor('scheduler.enabled')}
                    onChange={(checked) => updateDraft((next) => {
                        next.scheduler.enabled = checked
                    })}
                    help="Disabling this stops automatic indexing, monitoring and scheduled downloads after restart."
                    wide
                />
                <NumberField
                    id="settings-scheduler-workers"
                    label="Maximum workers"
                    value={draft.scheduler.maxWorkers}
                    min={1}
                    error={errorFor('scheduler.maxWorkers')}
                    environmentVariable={environmentVariableFor('scheduler.maxWorkers')}
                    onChange={(value) => updateDraft((next) => {
                        next.scheduler.maxWorkers = value
                    })}
                    help="Upper bound for parallel background task workers."
                />
                <DurationField
                    id="settings-scheduler-stalled-timeout"
                    label="Stalled task timeout"
                    value={draft.scheduler.stalledTaskTimeoutMinutes}
                    backendUnit="minutes"
                    error={errorFor('scheduler.stalledTaskTimeoutMinutes')}
                    environmentVariable={environmentVariableFor('scheduler.stalledTaskTimeoutMinutes')}
                    onChange={(value) => updateDraft((next) => {
                        next.scheduler.stalledTaskTimeoutMinutes = value
                    })}
                    help="Cancel a task or operation when its progress percentage has not changed for this long."
                />
                <NumberField
                    id="settings-scheduler-retries"
                    label="Default retries"
                    value={draft.scheduler.defaultMaxRetries}
                    min={0}
                    error={errorFor('scheduler.defaultMaxRetries')}
                    environmentVariable={environmentVariableFor('scheduler.defaultMaxRetries')}
                    onChange={(value) => updateDraft((next) => {
                        next.scheduler.defaultMaxRetries = value
                    })}
                    help="Used when a task or schedule does not specify its own retry count."
                />
                <DurationField
                    id="settings-scheduler-backoff"
                    label="Retry backoff"
                    value={draft.scheduler.retryBackoffSeconds}
                    backendUnit="seconds"
                    step={0.5}
                    error={errorFor('scheduler.retryBackoffSeconds')}
                    environmentVariable={environmentVariableFor('scheduler.retryBackoffSeconds')}
                    onChange={(value) => updateDraft((next) => {
                        next.scheduler.retryBackoffSeconds = value
                    })}
                    help="Base pause before retrying failed background work."
                />
            </SettingsSection>

            <SettingsSection
                title="Episode discovery and monitoring"
                description="Cron schedules used to find episodes and follow their publication state."
            >
                <CronEditor
                    id="settings-find-episodes-cron"
                    label="Find new episodes"
                    value={draft.newEpisodeSchedule.findEpisodesCron}
                    error={errorFor('newEpisodeSchedule.findEpisodesCron')}
                    environmentVariable={environmentVariableFor('newEpisodeSchedule.findEpisodesCron')}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.findEpisodesCron = value
                    })}
                    help={
                        <ReadMore summary={<span>Finds new episodes for every show indexed in WireLoft.</span>}>
                            <p>
                                This cron schedule determines how often WireLoft will search for new episodes across all shows.
                                It is recommended to set this to a value that is not too frequent, as it can impact performance.
                            </p>
                        </ReadMore>
                    }
                />
                <CronEditor
                    id="settings-monitor-pending-episode-cron"
                    label="Monitor pending episodes"
                    value={draft.newEpisodeSchedule.monitorPendingEpisodeCron}
                    error={errorFor('newEpisodeSchedule.monitorPendingEpisodeCron')}
                    environmentVariable={environmentVariableFor('newEpisodeSchedule.monitorPendingEpisodeCron')}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.monitorPendingEpisodeCron = value
                    })}
                    help={
                        <ReadMore summary={<span>Monitors scheduled, delayed, live, processing and countdown episodes.</span>}>
                            <p>
                                This cron schedule determines how often WireLoft monitors an episode after the <code>Find new episodes</code> worker
                                found it.
                            </p>
                            <p>
                                This worker is expected to run quite frequently. Make sure to not set it to run more often than once every two
                                minutes.
                            </p>
                            <p>
                                Once an episode becomes final, <code>Metadata refresh</code> takes over. If it enters <code>no_usable_media</code>,
                                the dedicated <code>No-usable-media monitor</code> takes over instead.
                            </p>
                        </ReadMore>
                    }
                />
                <CronEditor
                    id="settings-monitor-no-usable-media-episode-cron"
                    label="Monitor episodes without usable media"
                    value={draft.newEpisodeSchedule.monitorNoUsableMediaEpisodeCron}
                    error={errorFor('newEpisodeSchedule.monitorNoUsableMediaEpisodeCron')}
                    environmentVariable={environmentVariableFor('newEpisodeSchedule.monitorNoUsableMediaEpisodeCron')}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.monitorNoUsableMediaEpisodeCron = value
                    })}
                    help={
                        <ReadMore summary={<span>Rechecks every episode without usable media for recovery or confirmed removal.</span>}>
                            <p>
                                WireLoft rechecks all <code>no_usable_media</code> episodes on this schedule, regardless of why
                                they entered quarantine.
                            </p>
                            <p>
                                If this worker finds that the episode has usable media once again, it is restored and automatically
                                picked up by download- and stream profiles. If
                                after {' '}{formatDurationMinutes(draft.episodeStatusTiming.noUsableMediaDeleteAfterMinutes)} the
                                episode still did not return to The Daily Wire, it is deleted.
                            </p>
                        </ReadMore>
                    }
                />
                <TextField
                    id="settings-metadata-refresh-intervals"
                    label="Metadata refresh intervals"
                    value={draft.newEpisodeSchedule.metadataRefreshIntervals}
                    error={errorFor('newEpisodeSchedule.metadataRefreshIntervals')}
                    environmentVariable={environmentVariableFor('newEpisodeSchedule.metadataRefreshIntervals')}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.metadataRefreshIntervals = value
                    })}
                    help={
                        <ReadMore summary={<span>Intervals to refresh episode metadata after it is published.</span>}>
                            <p>
                                While a Daily Wire episode is live, WireLoft closely monitors it for status, title and thumbnail updates. After
                                publication, these targeted metadata refreshes keep reconciling late Daily Wire changes, including corrected episode
                                numbers.
                            </p>
                            <p>
                                Value is a list of comma-separated offsets after publication. Use s, m, h or d, for example: 120s,30m,3h,2d
                            </p>
                        </ReadMore>
                    }
                />
            </SettingsSection>

            <SettingsDisclosure
                title="Episode lifecycle timing"
                description="Fallback and cleanup thresholds used while Daily Wire episode state is settling."
            >
                <DurationField
                    id="settings-published-final"
                    label="Final publication threshold"
                    value={draft.episodeStatusTiming.publishedFinalAfterMinutes}
                    backendUnit="minutes"
                    error={errorFor('episodeStatusTiming.publishedFinalAfterMinutes')}
                    environmentVariable={environmentVariableFor('episodeStatusTiming.publishedFinalAfterMinutes')}
                    onChange={(value) => updateDraft((next) => {
                        next.episodeStatusTiming.publishedFinalAfterMinutes = value
                    })}
                    help={
                        <ReadMore summary={<span>Set to published final if still at published with countdown after this duration.</span>}>
                            <p>
                                Usually, WireLoft can determine an episode's status accurately. However, sometimes it might get stuck in <code>published
                                with countdown</code>.
                                If your download profiles are setup to only download <code>published final</code> episodes, this means they still skip
                                it. This setting acts
                                as a safety net to ensure <code>published with countdown</code> episodes eventually will always be considered <code>published
                                final</code>,
                                even if the conventional method of detecting this change failed.
                            </p>
                            <p>
                                This duration is measured starting from the time the episode was published.
                            </p>
                        </ReadMore>
                    }
                />
                <DurationField
                    id="settings-dw-processing-max"
                    label="Daily Wire processing safeguard"
                    value={draft.episodeStatusTiming.dwProcessingMaxMinutes}
                    backendUnit="minutes"
                    error={errorFor('episodeStatusTiming.dwProcessingMaxMinutes')}
                    environmentVariable={environmentVariableFor('episodeStatusTiming.dwProcessingMaxMinutes')}
                    onChange={(value) => updateDraft((next) => {
                        next.episodeStatusTiming.dwProcessingMaxMinutes = value
                    })}
                    help={
                        <ReadMore summary={<span>Set to no usable media if still at DW processing after this duration.</span>}>
                            <p>
                                Usually, WireLoft can determine an episode's status accurately. However, sometimes it might get stuck in <code>DW
                                processing</code>.
                                This setting acts as a safety net to ensure <code>DW processing</code> episodes will be considered <code>no usable
                                media</code> if
                                this duration elapsed without a change in <code>DW processing</code> status.
                            </p>
                            <p>
                                This duration is measured starting from the time the episode was published.
                            </p>
                        </ReadMore>
                    }
                />
                <DurationField
                    id="settings-no-usable-media-delete-after"
                    label="No usable media deletion delay"
                    value={draft.episodeStatusTiming.noUsableMediaDeleteAfterMinutes}
                    backendUnit="minutes"
                    error={errorFor('episodeStatusTiming.noUsableMediaDeleteAfterMinutes')}
                    environmentVariable={environmentVariableFor('episodeStatusTiming.noUsableMediaDeleteAfterMinutes')}
                    onChange={(value) => updateDraft((next) => {
                        next.episodeStatusTiming.noUsableMediaDeleteAfterMinutes = value
                    })}
                    help={
                        <ReadMore summary={<span>How long an episode may remain in no usable media state before it is deleted.</span>}>
                            <p>
                                An episode is considered in <code>no usable media</code> if it contains no media, its media is corrupted,
                                or if it returns <code>404</code> from The Daily Wire. In all of these case, this might be a temporary issue.
                                However, if it remains in this state after this duration, it may be deleted from WireLoft.
                            </p>
                            <p>
                                This duration is measured starting from the time the episode was marked as <code>no usable media</code>.
                            </p>
                        </ReadMore>
                    }
                />
            </SettingsDisclosure>
        </>
    )
}
