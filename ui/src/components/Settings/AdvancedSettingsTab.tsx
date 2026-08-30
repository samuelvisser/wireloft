import type {SettingsTabProps} from './SettingsTabTypes'
import {SettingsDisclosure, SettingsSection, TextField} from './SettingsControls'

export default function AdvancedSettingsTab({draft, updateDraft, environmentVariableFor}: SettingsTabProps) {
    return (
        <>
            <SettingsDisclosure
                title="Encryption key files"
                description="Paths used to retain encrypted DailyWire tokens and other protected values."
            >
                <TextField
                    id="settings-secret-key-file"
                    label="Secret key file override"
                    value={draft.crypto.secretKeyFile ?? ''}
                    environmentVariable={environmentVariableFor('crypto.secretKeyFile')}
                    onChange={(value) => updateDraft((next) => {
                        next.crypto.secretKeyFile = value || null
                    })}
                    placeholder="Leave empty to use the default key file"
                    help="WireLoft reads key material from this file instead of the generated default when set."
                    wide
                />
                <TextField
                    id="settings-default-secret-file"
                    label="Default generated key file"
                    value={draft.crypto.defaultSecretFile}
                    environmentVariable={environmentVariableFor('crypto.defaultSecretFile')}
                    onChange={(value) => updateDraft((next) => {
                        next.crypto.defaultSecretFile = value
                    })}
                    help="Changing encryption key files can make existing encrypted tokens unreadable. Restart WireLoft after changing this."
                    wide
                />
            </SettingsDisclosure>

            <SettingsSection
                title="Configuration precedence"
                description="WireLoft resolves a setting from the highest available source."
                className="settings-section--informational"
            >
                <ol className="settings-precedence-list settings-field--wide">
                    <li><strong>Environment variables</strong><span>Deployment-enforced values; affected UI controls are disabled</span></li>
                    <li><strong>config.yml</strong><span>Manual configuration and settings saved on this page</span></li>
                    <li><strong>Built-in defaults</strong><span>Used only when a setting is not otherwise configured</span></li>
                </ol>
            </SettingsSection>
        </>
    )
}
