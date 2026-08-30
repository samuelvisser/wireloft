import type {SettingsTabProps} from './SettingsTabTypes'
import {SettingsDisclosure, TextField} from './SettingsControls'

type AdvancedSettingsTabProps = SettingsTabProps & {
    hasOverrides: boolean
    isResetting: boolean
    onReset: () => void
}

export default function AdvancedSettingsTab({
    draft,
    updateDraft,
    hasOverrides,
    isResetting,
    onReset,
}: AdvancedSettingsTabProps) {
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
                    onChange={(value) => updateDraft((next) => {
                        next.crypto.defaultSecretFile = value
                    })}
                    help="Changing encryption key files can make existing encrypted tokens unreadable. Restart WireLoft after changing this."
                    wide
                />
            </SettingsDisclosure>

            <section className="settings-section settings-section--informational">
                <div className="settings-section__header">
                    <h2>Configuration precedence</h2>
                    <p>WireLoft resolves a setting from the highest available source.</p>
                </div>
                <ol className="settings-precedence-list">
                    <li><strong>Environment variables</strong><span>Deployment-enforced values</span></li>
                    <li><strong>Settings UI</strong><span>Values saved on this page</span></li>
                    <li><strong>config.yml</strong><span>Your file-managed base configuration</span></li>
                    <li><strong>Built-in defaults</strong><span>WireLoft defaults for unspecified values</span></li>
                </ol>
                <p className="settings-bootstrap-note">
                    Database location, application version and literal encryption key material remain file-managed bootstrap settings.
                </p>
            </section>

            <section className="settings-section settings-section--danger">
                <div className="settings-danger-row">
                    <div>
                        <h2>Reset UI overrides</h2>
                        <p>Delete the UI-managed settings file and immediately return to config.yml, environment and default values.</p>
                    </div>
                    <button
                        className="btn btn-danger"
                        type="button"
                        disabled={!hasOverrides || isResetting}
                        onClick={onReset}
                    >
                        {isResetting ? 'Resetting…' : 'Reset all UI settings'}
                    </button>
                </div>
            </section>
        </>
    )
}
