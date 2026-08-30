import type {SettingsTabProps} from './SettingsTabTypes'
import {
    NumberField,
    SettingsDisclosure,
    SettingsSection,
    TextField,
    ToggleField,
} from './SettingsControls'

export default function AutomationSettingsTab({draft, updateDraft}: SettingsTabProps) {
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
                <TextField
                    id="settings-find-episodes-cron"
                    label="Find new episodes"
                    value={draft.newEpisodeSchedule.findEpisodesCron}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.findEpisodesCron = value
                    })}
                    help="Five-part cron expression."
                />
                <TextField
                    id="settings-monitor-episode-cron"
                    label="Monitor pending episodes"
                    value={draft.newEpisodeSchedule.monitorEpisodeCron}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.monitorEpisodeCron = value
                    })}
                    help="Five-part cron expression."
                />
                <TextField
                    id="settings-no-show-today-cron"
                    label="Check no-show-today episodes"
                    value={draft.newEpisodeSchedule.checkNoShowTodayCron}
                    onChange={(value) => updateDraft((next) => {
                        next.newEpisodeSchedule.checkNoShowTodayCron = value
                    })}
                    help="Five-part cron expression."
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
                    onChange={(value) => updateDraft((next) => {
                        next.episodeStatusTiming.publishedFinalAfterMinutes = value
                    })}
                    help="Must be at least as long as the countdown publication threshold."
                />
            </SettingsDisclosure>
        </>
    )
}
