import type {SettingsTabProps} from './SettingsTabTypes'
import CronEditor from './CronEditor'
import {
    NumberField,
    SettingsDisclosure,
    SettingsSection,
    TextField,
    ToggleField,
} from './SettingsControls'

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
                    help="Comma-separated offsets after publication. Use s, m, h or d, for example: 5m,15m,30m,1h,3h,6h,24h."
                    wide
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
