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
                            <p>
                                Before treating a new slug as a new episode, WireLoft can conservatively reconcile it onto the
                                sole matching pending episode. This covers Daily Wire changing a slug before publication.
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
                                found it. It owns only the pending publication lifecycle.
                            </p>
                            <p>
                                Once an episode becomes final, metadata refresh takes over. If it enters <code>no_usable_media</code>,
                                the dedicated no-usable-media monitor takes over instead.
                            </p>
                            <p>
                                This worker is expected to run quite frequently. Make sure to not set it to run more often than once every two minutes.
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
                        <ReadMore summary={<span>Rechecks every quarantined episode for recovery or confirmed removal.</span>}>
                            <p>
                                WireLoft rechecks all <code>no_usable_media</code> episodes on this schedule, regardless of why
                                they entered quarantine. A responding Daily Wire episode remains stored until usable media returns.
                            </p>
                            <p>
                                Automatic deletion is only possible when Daily Wire currently returns 404 and the continuous
                                quarantine delay below has elapsed.
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
                                While a Daily Wire episode is live, WireLoft closely monitors it for status, title and thumbnail updates. After publication, these targeted metadata refreshes keep reconciling late Daily Wire changes, including corrected episode numbers.
                            </p>
                            <p>
                                Value is a list of comma-separated offsets after publication. Use s, m, h or d, for example: 120s,30m,3h,2d
                            </p>
                        </ReadMore>
                    } wide
                />
            </SettingsSection>

            <SettingsDisclosure
                title="Episode lifecycle timing"
                description="Fallback and cleanup thresholds used while Daily Wire episode state is settling."
            >
                <DurationField
                    id="settings-published-countdown"
                    label="Countdown publication threshold"
                    value={draft.episodeStatusTiming.publishedCountdownAfterMinutes}
                    backendUnit="minutes"
                    error={errorFor('episodeStatusTiming.publishedCountdownAfterMinutes')}
                    environmentVariable={environmentVariableFor('episodeStatusTiming.publishedCountdownAfterMinutes')}
                    onChange={(value) => updateDraft((next) => {
                        next.episodeStatusTiming.publishedCountdownAfterMinutes = value
                    })}
                    help="Existing publication timing setting retained for compatibility."
                />
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
                    help="Measured from Daily Wire publishedAt. Only an episode whose current remote state is still published-with-countdown is forced to published final after this threshold."
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
                    help="Measured from Daily Wire publishedAt. If the short-metadata/long-HLS processing signature remains after this threshold, WireLoft quarantines the episode as no_usable_media."
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
                    help="How long the continuous no_usable_media state must last before a current Daily Wire 404 may be deleted. A successful Daily Wire response is never automatically deleted."
                />
            </SettingsDisclosure>
        </>
    )
}
