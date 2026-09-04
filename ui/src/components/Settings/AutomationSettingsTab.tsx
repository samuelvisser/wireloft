import type {SettingsTabProps} from './SettingsTabTypes'
import CronEditor from './CronEditor'
import {
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
                <NumberField
                    id="settings-scheduler-stalled-timeout"
                    label="Stalled task timeout"
                    value={draft.scheduler.stalledTaskTimeoutMinutes}
                    min={1}
                    unit="minutes"
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
                <NumberField
                    id="settings-scheduler-backoff"
                    label="Retry backoff"
                    value={draft.scheduler.retryBackoffSeconds}
                    min={0}
                    step={0.5}
                    unit="seconds"
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
                    id="settings-monitor-episode-cron"
                    label="Monitor pending episodes"
                    value={draft.newEpisodeSchedule.monitorEpisodeCron}
                    error={errorFor('newEpisodeSchedule.monitorEpisodeCron')}
                    environmentVariable={environmentVariableFor('newEpisodeSchedule.monitorEpisodeCron')}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.monitorEpisodeCron = value
                    })}
                    help={
                        <ReadMore summary={<span>Monitors currently live or scheduled episodes.</span>}>
                            <p>
                                This cron schedule determines how often WireLoft will monitor an episode after the <code>Find new episodes</code> worker
                                found it. As long as the episode is either scheduled or live, WireLoft checks on its status very frequently.
                                This makes sure that any changes in it's status get picked up quickly, and the download- and stream profiles
                                can serve you the episode as soon as possible.
                            </p>
                            <p>
                                This worker is expected to run quite frequently. It is as lightweight as possible, should not impact performance much
                                or annoying the Daily Wire API. Make sure to not set it to run more often than once every two minutes though.
                            </p>
                            <p>
                                <code>Monitor pending episodes</code> never runs on episodes that are not pending.
                            </p>
                        </ReadMore>
                    }
                />
                <CronEditor
                    id="settings-no-show-today-cron"
                    label="Check no-show-today episodes"
                    value={draft.newEpisodeSchedule.checkNoShowTodayCron}
                    error={errorFor('newEpisodeSchedule.checkNoShowTodayCron')}
                    environmentVariable={environmentVariableFor('newEpisodeSchedule.checkNoShowTodayCron')}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.checkNoShowTodayCron = value
                    })}
                    help={
                        <ReadMore summary={<span>How often to check for no-show-today episodes.</span>}>
                            <p>
                                The Daily Wire does this annoying thing where they sometimes 'publish' an episode just to tell
                                everyone there will not be any episodes today. This cron schedule runs infrequently and checks
                                if any of the new episodes are no-show-today episodes. It removes them from WireLoft when found.
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
                        <ReadMore summary={<span>Intervals to refresh episode metadata after its published.</span>}>
                            <p>
                                While a Daily Wire episode is live, WireLoft closely monitors it for any status updates, title changes or new
                                thumbnails. When it is published, this metadata refresh is our next approach.
                            </p>
                            <p>
                                Show episodes sometimes do not yet contain their final thumbnail even when they are fully published. Other times,
                                their title might change a little after publication. For these cases,
                                WireLoft automatically updates episode metadata at a couple intervals after its publication. Here, you can configure
                                those intervals.
                            </p>
                            <p>
                                Value is a list of comma-separated offsets after publication. Use s, m, h or d, for example: 120s,30m,3h,2d
                            </p>
                        </ReadMore>
                    } wide
                />
            </SettingsSection>

            <SettingsDisclosure
                title="Episode publication timing"
                description="Thresholds used while a newly published episode is still settling on DailyWire."
            >
                <NumberField
                    id="settings-published-countdown"
                    label="Countdown publication threshold"
                    value={draft.episodeStatusTiming.publishedCountdownAfterMinutes}
                    min={0}
                    unit="minutes"
                    error={errorFor('episodeStatusTiming.publishedCountdownAfterMinutes')}
                    environmentVariable={environmentVariableFor('episodeStatusTiming.publishedCountdownAfterMinutes')}
                    onChange={(value) => updateDraft((next) => {
                        next.episodeStatusTiming.publishedCountdownAfterMinutes = value
                    })}
                    help="When a scheduled episode may first be treated as published while final media is still processing."
                />
                <NumberField
                    id="settings-published-final"
                    label="Final publication threshold"
                    value={draft.episodeStatusTiming.publishedFinalAfterMinutes}
                    min={0}
                    unit="minutes"
                    error={errorFor('episodeStatusTiming.publishedFinalAfterMinutes')}
                    environmentVariable={environmentVariableFor('episodeStatusTiming.publishedFinalAfterMinutes')}
                    onChange={(value) => updateDraft((next) => {
                        next.episodeStatusTiming.publishedFinalAfterMinutes = value
                    })}
                    help="Must be at least as long as the countdown publication threshold."
                />
            </SettingsDisclosure>
        </>
    )
}
