import type {SettingsValues} from '../../types/schemas/settings'
import type {SettingsTabProps} from './SettingsTabTypes'
import {
    DurationField,
    SelectField,
    SettingsSection,
    TextField,
} from './SettingsControls'

export default function GeneralSettingsTab({draft, updateDraft, environmentVariableFor, errorFor}: SettingsTabProps) {
    return (
        <>
            <SettingsSection
                title="Application"
                description="Common settings that affect WireLoft throughout the interface and background services."
            >
                <TextField
                    id="settings-timezone"
                    label="Timezone"
                    value={draft.timezone}
                    error={errorFor('timezone')}
                    environmentVariable={environmentVariableFor('timezone')}
                    onChange={(value) => updateDraft((next) => { next.timezone = value })}
                    help={<>Use an <a href="https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List">IANA</a> timezone such as <code>Europe/Amsterdam</code>.</>}
                />
                <SelectField
                    id="settings-log-level"
                    label="Log level"
                    value={draft.logLevel}
                    options={['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']}
                    error={errorFor('logLevel')}
                    environmentVariable={environmentVariableFor('logLevel')}
                    onChange={(value) => updateDraft((next) => {
                        next.logLevel = value as SettingsValues['logLevel']
                    })}
                    help="DEBUG is useful for troubleshooting but produces substantially more output."
                />
            </SettingsSection>

            <SettingsSection
                title="Login session"
                description="Controls how long a signed-in browser remains authenticated."
            >
                <DurationField
                    id="settings-session-ttl"
                    label="Session lifetime"
                    value={draft.loginSession.ttlSeconds}
                    backendUnit="seconds"
                    error={errorFor('loginSession.ttlSeconds')}
                    environmentVariable={environmentVariableFor('loginSession.ttlSeconds')}
                    onChange={(value) => updateDraft((next) => {
                        next.loginSession.ttlSeconds = value
                    })}
                />
            </SettingsSection>
        </>
    )
}
