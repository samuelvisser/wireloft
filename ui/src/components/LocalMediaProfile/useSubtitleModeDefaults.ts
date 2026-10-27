import {useEffect, useRef} from 'react'
import type {UseFormReturn} from 'react-hook-form'

import {
    defaultSubtitleModeForProfile,
    type LocalMediaProfileType,
    type ShowLocalMediaProfileScope,
} from '../../types/local_media_profile'
import type {LocalMediaProfileSubtitleMode} from '../../types/schemas/local_media_profile_base'

/**
 * Scope and profile type are initial suggestions, not persistent inheritance:
 * once the user chooses a subtitle mode, changing scope/type must not overwrite it.
 *
 * Only new profiles have automatic defaults. Existing profiles always retain
 * their saved subtitle mode, even when their availability changes.
 * In the Add Profile page, the two profile types have separate RHF forms, so
 * an explicit choice must follow the user when switching between them.
 */
export function useSubtitleModeDefaults(
    form: UseFormReturn<any>,
    mode: LocalMediaProfileType,
    isCreating: boolean,
) {
    const manuallySelected = useRef<LocalMediaProfileSubtitleMode | null>(null)
    const previous = useRef({form, mode})

    useEffect(() => {
        if (!isCreating) {
            previous.current = {form, mode}
            return
        }
        const prior = previous.current
        if (prior.form !== form || prior.mode !== mode) {
            const priorValue = prior.form.getValues('subtitleMode') as LocalMediaProfileSubtitleMode | undefined
            const priorDefault = defaultSubtitleModeForProfile(
                prior.mode,
                prior.form.getValues('showScope') as ShowLocalMediaProfileScope,
            )
            if (manuallySelected.current === null && priorValue && priorValue !== priorDefault) {
                manuallySelected.current = priorValue
            }

            const nextValue = manuallySelected.current ?? defaultSubtitleModeForProfile(
                mode, form.getValues('showScope') as ShowLocalMediaProfileScope,
            )
            form.setValue('subtitleMode', nextValue, {shouldDirty: true, shouldValidate: true})
        }
        previous.current = {form, mode}
    }, [form, mode, isCreating])

    const onSubtitleModeChange = (value: LocalMediaProfileSubtitleMode) => {
        if (isCreating) manuallySelected.current = value
    }

    const onScopeChange = (nextScope: ShowLocalMediaProfileScope) => {
        if (!isCreating) return
        if (manuallySelected.current === null) {
            const currentValue = form.getValues('subtitleMode') as LocalMediaProfileSubtitleMode | undefined
            const previousDefault = defaultSubtitleModeForProfile(
                mode, form.getValues('showScope') as ShowLocalMediaProfileScope,
            )
            if (currentValue && currentValue !== previousDefault) {
                manuallySelected.current = currentValue
            }
        }

        if (manuallySelected.current === null) {
            form.setValue('subtitleMode', defaultSubtitleModeForProfile('show', nextScope), {
                shouldDirty: true,
                shouldValidate: true,
            })
        }
    }

    return {onSubtitleModeChange, onScopeChange}
}
