import type {SettingsValues} from '../../types/schemas/settings'


export type UpdateSettingsDraft = (mutator: (next: SettingsValues) => void) => void

export type SettingsTabProps = {
    draft: SettingsValues
    updateDraft: UpdateSettingsDraft
}
