import type {SettingsTabProps} from './SettingsTabTypes'
import {NumberField, SettingsDisclosure, TextField} from './SettingsControls'

const TMDB_LOGO_URL = 'https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.svg'

export default function AdvancedSettingsTab({draft, updateDraft, environmentVariableFor}: SettingsTabProps) {
    const tokenEnvironmentVariable = environmentVariableFor('movieMetadata.tmdbReadAccessToken')
    const tokenConfigured = draft.movieMetadata.tmdbReadAccessTokenConfigured || Boolean(tokenEnvironmentVariable)

    return (
        <>
            <SettingsDisclosure
                title="Movie metadata (TMDB)"
                description="Release-date metadata used for movie file naming and media-server matching."
            >
                <TextField
                    id="settings-tmdb-token"
                    label="TMDB API Read Access Token"
                    value={draft.movieMetadata.tmdbReadAccessToken}
                    environmentVariable={tokenEnvironmentVariable}
                    onChange={(value) => updateDraft((next) => {
                        next.movieMetadata.tmdbReadAccessToken = value
                    })}
                    placeholder={tokenConfigured ? 'Token configured — enter a new token to replace it' : 'Enter a TMDB API Read Access Token'}
                    help={tokenConfigured
                        ? 'A token is configured. WireLoft never returns the stored token to the browser; entering a value here replaces it.'
                        : 'Required for one-time release-date lookup when a movie is first added to WireLoft.'}
                    inputType="password"
                    autoComplete="new-password"
                    wide
                />
                <TextField
                    id="settings-tmdb-api-url"
                    label="TMDB API URL"
                    value={draft.movieMetadata.tmdbApiBaseUrl}
                    environmentVariable={environmentVariableFor('movieMetadata.tmdbApiBaseUrl')}
                    onChange={(value) => updateDraft((next) => {
                        next.movieMetadata.tmdbApiBaseUrl = value
                    })}
                    help="Normally leave this at the official TMDB API endpoint."
                    wide
                />
                <TextField
                    id="settings-tmdb-language"
                    label="Metadata language"
                    value={draft.movieMetadata.language}
                    environmentVariable={environmentVariableFor('movieMetadata.language')}
                    onChange={(value) => updateDraft((next) => {
                        next.movieMetadata.language = value
                    })}
                    placeholder="en-US"
                    help="Language supplied to TMDB while matching movie metadata."
                />
                <NumberField
                    id="settings-tmdb-timeout"
                    label="Request timeout"
                    value={draft.movieMetadata.requestTimeoutSeconds}
                    environmentVariable={environmentVariableFor('movieMetadata.requestTimeoutSeconds')}
                    onChange={(value) => updateDraft((next) => {
                        next.movieMetadata.requestTimeoutSeconds = value
                    })}
                    min={1}
                    step={1}
                    unit="seconds"
                />
                <NumberField
                    id="settings-tmdb-retries"
                    label="Retry attempts"
                    value={draft.movieMetadata.maxRetries}
                    environmentVariable={environmentVariableFor('movieMetadata.maxRetries')}
                    onChange={(value) => updateDraft((next) => {
                        next.movieMetadata.maxRetries = value
                    })}
                    min={0}
                    step={1}
                    help="Retries transient TMDB failures before recording the lookup as failed."
                />
                <div className="settings-field settings-field--wide">
                    <div className="settings-field__help" style={{display: 'flex', alignItems: 'center', gap: 12}}>
                        <a href="https://www.themoviedb.org/" target="_blank" rel="noreferrer" aria-label="Open TMDB">
                            <img src={TMDB_LOGO_URL} alt="TMDB" width="52" height="38"/>
                        </a>
                        <span>This product uses the TMDB API but is not endorsed or certified by TMDB.</span>
                    </div>
                </div>
            </SettingsDisclosure>

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

            <section className="settings-section settings-section--informational">
                <div className="settings-section__header">
                    <h2>Configuration precedence</h2>
                    <p>WireLoft resolves a setting from the highest available source.</p>
                </div>
                <ol className="settings-precedence-list">
                    <li><strong>Environment variables</strong><span>Deployment-enforced values; affected UI controls are disabled</span></li>
                    <li><strong>config.yml</strong><span>Manual configuration and settings saved on this page</span></li>
                    <li><strong>Built-in defaults</strong><span>Used only when a setting is not otherwise configured</span></li>
                </ol>
            </section>
        </>
    )
}
