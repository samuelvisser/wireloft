import {useEffect, useState} from 'react'
import Switch from 'react-switch'

type Props = {
    checked: boolean
    ariaLabel: string
    onChange: (checked: boolean) => Promise<void>
}

export default function ProfileEnabledSwitch({checked, ariaLabel, onChange}: Props) {
    const [optimisticChecked, setOptimisticChecked] = useState(checked)
    const [isUpdating, setIsUpdating] = useState(false)

    useEffect(() => {
        if (!isUpdating) setOptimisticChecked(checked)
    }, [checked, isUpdating])

    const handleChange = async (nextChecked: boolean) => {
        if (isUpdating) return

        const previousChecked = optimisticChecked
        setOptimisticChecked(nextChecked)
        setIsUpdating(true)

        try {
            await onChange(nextChecked)
        } catch {
            setOptimisticChecked(previousChecked)
        } finally {
            setIsUpdating(false)
        }
    }

    return (
        <span
            style={{display: 'inline-flex'}}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
        >
            <Switch
                checked={optimisticChecked}
                disabled={isUpdating}
                onChange={handleChange}
                onColor="#0ea5e9"
                offColor="#d1d5db"
                uncheckedIcon={false}
                checkedIcon={false}
                aria-label={ariaLabel}
            />
        </span>
    )
}
