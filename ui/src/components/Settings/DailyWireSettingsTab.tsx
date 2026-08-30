import DailywireAuthCard from '../DailywireAuth/DailywireAuthCard'
import type {SettingsTabProps} from './SettingsTabTypes'
import {NumberField, SettingsDisclosure, TextField} from './SettingsControls'

export default function DailyWireSettingsTab({draft, updateDraft, environmentVariableFor}: SettingsTabProps) {
    return (
        <>
            <DailywireAuthCard />

            <SettingsDisclosure
                title="DailyWire API endpoints"
                description="Normally only change these for development, proxies or a DailyWire API migration."
            >
                <TextField
                    id="settings-dw-middleware-api"
                    label="Middleware API"
                    value={draft.dwApi.middlewareApi}
                    environmentVariable={environmentVariableFor('dwApi.middlewareApi')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwApi.middlewareApi = value
                    })}
                    wide
                />
                <TextField
                    id="settings-dw-stream-api"
                    label="Stream API"
                    value={draft.dwApi.streamApi}
                    environmentVariable={environmentVariableFor('dwApi.streamApi')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwApi.streamApi = value
                    })}
                    wide
                />
            </SettingsDisclosure>

            <SettingsDisclosure
                title="OAuth client"
                description="Device-login identity and requested authorization scope."
            >
                <TextField
                    id="settings-oauth-issuer"
                    label="Issuer"
                    value={draft.dwOauth.issuer}
                    environmentVariable={environmentVariableFor('dwOauth.issuer')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwOauth.issuer = value
                    })}
                    wide
                />
                <TextField
                    id="settings-oauth-audience"
                    label="Audience"
                    value={draft.dwOauth.audience}
                    environmentVariable={environmentVariableFor('dwOauth.audience')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwOauth.audience = value
                    })}
                    wide
                />
                <TextField
                    id="settings-oauth-client-id"
                    label="Client ID"
                    value={draft.dwOauth.clientId}
                    environmentVariable={environmentVariableFor('dwOauth.clientId')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwOauth.clientId = value
                    })}
                    wide
                />
                <TextField
                    id="settings-oauth-scope"
                    label="Scope"
                    value={draft.dwOauth.scope}
                    environmentVariable={environmentVariableFor('dwOauth.scope')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwOauth.scope = value
                    })}
                    wide
                />
            </SettingsDisclosure>

            <SettingsDisclosure
                title="Request pacing"
                description="Rate-control thresholds used when WireLoft talks to DailyWire."
            >
                <NumberField
                    id="settings-fast-request-delay"
                    label="Minimum fast-request delay"
                    value={draft.dwTimeout.minFastRequestMs}
                    min={0}
                    unit="ms"
                    environmentVariable={environmentVariableFor('dwTimeout.minFastRequestMs')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwTimeout.minFastRequestMs = value
                    })}
                />
                <NumberField
                    id="settings-max-fast-requests"
                    label="Fast requests before slowdown"
                    value={draft.dwTimeout.maxFastRequests}
                    min={1}
                    environmentVariable={environmentVariableFor('dwTimeout.maxFastRequests')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwTimeout.maxFastRequests = value
                    })}
                />
                <NumberField
                    id="settings-slow-request-delay"
                    label="Minimum slow-request delay"
                    value={draft.dwTimeout.minSlowRequestMs}
                    min={0}
                    unit="ms"
                    environmentVariable={environmentVariableFor('dwTimeout.minSlowRequestMs')}
                    onChange={(value) => updateDraft((next) => {
                        next.dwTimeout.minSlowRequestMs = value
                    })}
                />
            </SettingsDisclosure>
        </>
    )
}
