import type {SettingsValues} from '../../types/schemas/settings'
import type {SettingsTabProps} from './SettingsTabTypes'
import {
    humanizeSeconds,
    NumberField,
    SelectField,
    SettingsSection,
    TextField,
} from './SettingsControls'

export default function GeneralSettingsTab({draft, updateDraft}: SettingsTabProps) {
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
                    onChange={(value) => updateDraft((next) => { next.timezone = value })}
                    help={<>Use an IANA timezone such as <code>Europe/Amsterdam</code>.</>}
                />
                <SelectField
                    id="settings-log-level"
                    label="Log level"
                    value={draft.logLevel}
                    options={['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']}
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
                <NumberField
                    id="settings-session-ttl"
                    label="Session lifetime"
                    value={draft.loginSession.ttlSeconds}
                    min={60}
                    unit="seconds"
                    onChange={(value) => updateDraft((next) => {
                        next.loginSession.ttlSeconds = value
                    })}
                    help={`Currently ${humanizeSeconds(draft.loginSession.ttlSeconds)}.`}
                />
            </SettingsSection>
        </>
    )
}
