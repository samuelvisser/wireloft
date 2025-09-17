import { useEffect, useMemo } from 'react'
import Switch from 'react-switch'
import { Controller, useForm, type UseFormSetError } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  MediaProfileCreateSchema,
  MediaProfileUpdateSchema,
} from '../../types/schemas/media_profile'

export type MediaProfileFormValue = z.infer<typeof MediaProfileCreateSchema>

type Props = {
  value: MediaProfileFormValue
  onChange: (v: MediaProfileFormValue) => void
  autoFocusName?: boolean
  mode?: 'create' | 'update'
  onRegisterSetError?: (setError: UseFormSetError<MediaProfileFormValue>) => void
}

export default function MediaProfileForm({
  value,
  onChange,
  autoFocusName,
  mode = 'create',
  onRegisterSetError,
}: Props) {
  const schema = useMemo(() => (mode === 'update' ? MediaProfileUpdateSchema : MediaProfileCreateSchema), [mode])

  const { register, control, formState: { errors }, watch, reset, setError } = useForm<MediaProfileFormValue>({
    resolver: zodResolver(schema),
    defaultValues: value,
    mode: 'onBlur',
    reValidateMode: 'onChange',
  })

  // Keep RHF in sync if parent value changes (e.g., when editing)
  useEffect(() => {
    reset(value)
  }, [value, reset])

  // Propagate form changes up to parent state
  useEffect(() => {
    const sub = watch((v) => {
      onChange(v as MediaProfileFormValue)
    })
    return () => sub.unsubscribe()
  }, [watch, onChange])

  // Expose setError to parent so it can map server-side validation errors
  useEffect(() => {
    if (onRegisterSetError) onRegisterSetError(setError)
  }, [onRegisterSetError, setError])

  return (
    <>
      <div className="form-row">
        <label htmlFor="mp-name">Name</label>
        <input
          id="mp-name"
          className="input"
          type="text"
          placeholder="My 4k Profile"
          autoFocus={autoFocusName}
          {...register('name')}
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? 'mp-name-validate' : undefined}
        />
        {errors.name && (
          <div id="mp-name-validate" className="help" role="alert" aria-live="polite">
            {errors.name.message as string}
          </div>
        )}
      </div>

      <div className="form-row">
        <label htmlFor="mp-path">Output path template</label>
        <input
          id="mp-path"
          className="input"
          type="text"
          placeholder="D:/Media/Shows/{show}/{season}"
          {...register('outputTemplate')}
          aria-invalid={!!errors.outputTemplate}
          aria-describedby={errors.outputTemplate ? 'mp-path-error' : undefined}
        />
        {errors.outputTemplate && (
          <div id="mp-path-error" className="help" role="alert" aria-live="polite">
            {errors.outputTemplate.message as string}
          </div>
        )}
        <div className="help">Use placeholders like {`{show}`} and {`{season}`}.</div>
      </div>

      <div className="form-row">
        <label htmlFor="mp-format">Preferred format</label>
        <select id="mp-format" className="input" {...register('preferredFormat')}>
          <option value="4k">4k</option>
          <option value="1080p">1080p</option>
          <option value="720p">720p</option>
          <option value="audio_only">Audio Only</option>
        </select>
      </div>

      <div className="form-row" style={{ alignItems: 'center' }}>
        <label htmlFor="mp-images">Download series images</label>
        <Controller
          control={control}
          name="downloadSeriesImages"
          render={({ field: { value: checked, onChange: setChecked } }) => (
            <Switch
              id="mp-images"
              checked={!!checked}
              onChange={(c) => setChecked(c)}
              onColor="#0ea5e9"
              offColor="#d1d5db"
              uncheckedIcon={false}
              checkedIcon={false}
            />
          )}
        />
      </div>
    </>
  )
}
