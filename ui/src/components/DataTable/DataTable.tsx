import {CSSProperties, HTMLAttributes, ReactNode, useEffect, useMemo, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'

export type Column<T> = {
    id?: string
    header: ReactNode
    accessor?: keyof T | ((row: T) => ReactNode)
    cell?: (row: T) => ReactNode
    width?: number | string
    align?: 'left' | 'right' | 'center'
    headerStyle?: CSSProperties
    cellStyle?: CSSProperties
    dataLabel?: string
}

export type DataTableAction<T> = {
    onClick: (row: T) => void
    icon: IconProp
    text: string
    classes?: string
}

export type DataTableProps<T> = {
    columns: Column<T>[]
    data?: T[]
    loading?: boolean
    error?: unknown
    ariaLabel: string
    loadingMessage?: string
    emptyMessage?: string
    rowKey: (row: T) => string | number
    onRowClick?: (row: T) => void
    rowAriaLabel?: (row: T) => string
    getRowProps?: (row: T) => HTMLAttributes<HTMLTableRowElement>
    className?: string
    wrapperClassName?: string
    actions?: (row: T) => DataTableAction<T>[]
}

export function DataTable<T>(props: DataTableProps<T>) {
    const {
        columns,
        data,
        loading,
        error,
        ariaLabel,
        loadingMessage = 'Loading... ',
        emptyMessage = 'No data found',
        rowKey,
        onRowClick,
        rowAriaLabel,
        getRowProps,
        className,
        wrapperClassName,
        actions,
    } = props

    const [isMobile, setIsMobile] = useState<boolean>(typeof window !== 'undefined' ? window.innerWidth <= 640 : false)
    useEffect(() => {
        if (typeof window === 'undefined') return
        const onResize = () => setIsMobile(window.innerWidth <= 640)
        window.addEventListener('resize', onResize)
        return () => window.removeEventListener('resize', onResize)
    }, [])

    const colSpan = useMemo(() => (columns.length + (actions ? 1 : 0)) || 1, [columns, actions])

    return (
        <div className={wrapperClassName ?? 'table-wrapper'}>
            <table className={className ?? 'table'} aria-label={ariaLabel}>
                <thead>
                <tr>
                    {columns.map((c, idx) => {
                        const style: CSSProperties = {
                            width: c.width,
                            textAlign: c.align,
                            ...c.headerStyle,
                        }
                        return (
                            <th key={c.id ?? String(idx)} scope="col" style={style}>
                                {c.header}
                            </th>
                        )
                    })}
                    {actions && (
                        <th key="actions" scope="col" style={{width: 100, textAlign: 'right'}}>Actions</th>
                    )}
                </tr>
                </thead>
                <tbody>
                {loading && (!data || data.length === 0) ? (
                    <tr>
                        <td colSpan={colSpan}>{loadingMessage}</td>
                    </tr>
                ) : !data || data.length === 0 ? (
                    <tr>
                        <td colSpan={colSpan}>{(error as any)?.message ?? emptyMessage}</td>
                    </tr>
                ) : (
                    data.map((row) => {
                        const clickable = Boolean(onRowClick)
                        const rowKeyValue = String(rowKey(row))
                        const rowProps: HTMLAttributes<HTMLTableRowElement> = {
                            ...(getRowProps ? getRowProps(row) : {}),
                        }
                        if (clickable) {
                            rowProps.tabIndex = rowProps.tabIndex ?? 0
                            rowProps.style = {cursor: 'pointer', ...(rowProps.style || {})}
                            rowProps.onClick = (e) => {
                                // Preserve any external onClick
                                if (getRowProps && getRowProps(row)?.onClick) {
                                    getRowProps(row)!.onClick!(e)
                                    if (e.defaultPrevented) return
                                }
                                onRowClick?.(row)
                            }
                            rowProps.onKeyDown = (e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault()
                                    onRowClick?.(row)
                                }
                            }
                        }
                        const aria = rowAriaLabel?.(row)
                        if (aria) (rowProps as any)['aria-label'] = aria

                        return (
                            <tr key={rowKeyValue} {...rowProps}>
                                {columns.map((c, idx) => {
                                    const content: ReactNode =
                                        c.cell
                                            ? c.cell(row)
                                            : typeof c.accessor === 'function'
                                                ? c.accessor(row)
                                                : c.accessor
                                                    ? (row as any)[c.accessor as any]
                                                    : null
                                    const style: CSSProperties = {
                                        textAlign: c.align,
                                        ...c.cellStyle,
                                    }
                                    return (
                                        <td key={(c.id ?? String(idx)) + '-cell'} style={style} data-label={c.dataLabel ?? String(c.header)}>
                                            {content}
                                        </td>
                                    )
                                })}
                                {actions && (
                                    <td key={'actions-cell'} style={{textAlign: 'right'}} data-label={'Actions'}>
                                        <div style={{display: 'inline-flex', gap: 6, flexWrap: 'wrap'}}>
                                            {actions(row).map((a, i) => (
                                                <button
                                                    key={i}
                                                    type="button"
                                                    className={isMobile ? (a.classes ?? 'btn') : 'icon-btn'}
                                                    aria-label={!isMobile ? `${a.text}${rowAriaLabel ? ' ' + (rowAriaLabel(row) ?? '') : ''}` : undefined}
                                                    title={!isMobile ? a.text : undefined}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        a.onClick(row)
                                                    }}
                                                >
                                                    {isMobile ? (
                                                        a.text
                                                    ) : (
                                                        <FontAwesomeIcon icon={a.icon}/>
                                                    )}
                                                </button>
                                            ))}
                                        </div>
                                    </td>
                                )}
                            </tr>
                        )
                    })
                )}
                </tbody>
            </table>
        </div>
    )
}

export default DataTable
