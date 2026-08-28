import {CSSProperties, HTMLAttributes, ReactNode, useId, useMemo, useState} from 'react'
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
    /** Hide this column from the expanded mobile details (usually the title shown in mobileSummary). */
    mobileHidden?: boolean
    /** When set, the column header becomes clickable and sorts rows by this value. */
    sortAccessor?: (row: T) => string | number | Date | null | undefined
}

type SortDirection = 'asc' | 'desc'
type SortState = { id: string; direction: SortDirection }

function compareSortValues(a: string | number | Date, b: string | number | Date): number {
    if (a instanceof Date && b instanceof Date) return a.getTime() - b.getTime()
    if (typeof a === 'number' && typeof b === 'number') return a - b
    return String(a).localeCompare(String(b), undefined, {sensitivity: 'base', numeric: true})
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
    /** Compact, always-visible content at the top of each mobile accordion card. */
    mobileSummary?: (row: T) => ReactNode
    /** Adds a mobile-only action that invokes onRowClick after the card is expanded. */
    mobileRowActionLabel?: string
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
        mobileSummary,
        mobileRowActionLabel,
    } = props

    const tableId = useId().replace(/:/g, '')
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

    const colSpan = useMemo(() => (columns.length + (actions ? 1 : 0)) || 1, [columns, actions])

    const [sortState, setSortState] = useState<SortState | null>(null)
    const toggleSort = (id: string) => {
        setSortState((prev) => {
            if (!prev || prev.id !== id) return {id, direction: 'asc'}
            if (prev.direction === 'asc') return {id, direction: 'desc'}
            return null
        })
    }

    const sortedData = useMemo(() => {
        if (!data || !sortState) return data
        const col = columns.find((c, idx) => (c.id ?? String(idx)) === sortState.id)
        const accessor = col?.sortAccessor
        if (!accessor) return data
        const dir = sortState.direction === 'asc' ? 1 : -1
        return [...data].sort((rowA, rowB) => {
            const a = accessor(rowA)
            const b = accessor(rowB)
            const aEmpty = a === null || a === undefined
            const bEmpty = b === null || b === undefined
            if (aEmpty && bEmpty) return 0
            if (aEmpty) return 1
            if (bEmpty) return -1
            return compareSortValues(a, b) * dir
        })
    }, [data, sortState, columns])

    const cellContent = (column: Column<T>, row: T): ReactNode =>
        column.cell
            ? column.cell(row)
            : typeof column.accessor === 'function'
                ? column.accessor(row)
                : column.accessor
                    ? (row as any)[column.accessor as any]
                    : null

    const toggleMobileRow = (key: string) => {
        setExpandedRows((previous) => {
            const next = new Set(previous)
            if (next.has(key)) next.delete(key)
            else next.add(key)
            return next
        })
    }

    const renderMobileMessage = () => {
        if (loading && (!sortedData || sortedData.length === 0)) return loadingMessage
        if (!sortedData || sortedData.length === 0) return (error as any)?.message ?? emptyMessage
        return null
    }

    return (
        <div className={wrapperClassName ?? 'table-wrapper'}>
            <table className={`${className ?? 'table'} desktop-data-table`} aria-label={ariaLabel}>
                <thead>
                <tr>
                    {columns.map((c, idx) => {
                        const id = c.id ?? String(idx)
                        const style: CSSProperties = {
                            width: c.width,
                            textAlign: c.align,
                            ...c.headerStyle,
                        }
                        if (!c.sortAccessor) {
                            return (
                                <th key={id} scope="col" style={style}>
                                    {c.header}
                                </th>
                            )
                        }
                        const isSorted = sortState?.id === id
                        const direction = isSorted ? sortState!.direction : undefined
                        const sortIcon = direction === 'asc' ? (['fas', 'sort-up'] as const) : direction === 'desc' ? (['fas', 'sort-down'] as const) : (['fas', 'sort'] as const)
                        return (
                            <th key={id} scope="col" style={style} aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none'}>
                                <button type="button" className="th-sort-btn" onClick={() => toggleSort(id)}>
                                    <span>{c.header}</span>
                                    <FontAwesomeIcon className="th-sort-icon" icon={sortIcon as any}/>
                                </button>
                            </th>
                        )
                    })}
                    {actions && (
                        <th key="actions" scope="col" style={{width: 100, textAlign: 'right'}}>Actions</th>
                    )}
                </tr>
                </thead>
                <tbody>
                {loading && (!sortedData || sortedData.length === 0) ? (
                    <tr>
                        <td colSpan={colSpan}>{loadingMessage}</td>
                    </tr>
                ) : !sortedData || sortedData.length === 0 ? (
                    <tr>
                        <td colSpan={colSpan}>{(error as any)?.message ?? emptyMessage}</td>
                    </tr>
                ) : (
                    sortedData.map((row) => {
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
                                    const content = cellContent(c, row)
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
                                                    className="icon-btn"
                                                    aria-label={`${a.text}${rowAriaLabel ? ' ' + (rowAriaLabel(row) ?? '') : ''}`}
                                                    title={a.text}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        a.onClick(row)
                                                    }}
                                                >
                                                    <FontAwesomeIcon icon={a.icon}/>
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

            <div className="mobile-data-list" role="list" aria-label={ariaLabel}>
                {renderMobileMessage() ? (
                    <div className="mobile-data-message">{renderMobileMessage()}</div>
                ) : (
                    sortedData?.map((row, rowIndex) => {
                        const rowKeyValue = String(rowKey(row))
                        const isExpanded = expandedRows.has(rowKeyValue)
                        const detailsId = `${tableId}-details-${rowIndex}`
                        const rowActions = actions?.(row) ?? []

                        return (
                            <article className={`mobile-data-card${isExpanded ? ' is-expanded' : ''}`} role="listitem" key={rowKeyValue}>
                                <button
                                    type="button"
                                    className="mobile-data-summary"
                                    aria-expanded={isExpanded}
                                    aria-controls={detailsId}
                                    aria-label={rowAriaLabel ? `${rowAriaLabel(row)} details` : undefined}
                                    onClick={() => toggleMobileRow(rowKeyValue)}
                                >
                                    <span className="mobile-data-summary-content">
                                        {mobileSummary ? mobileSummary(row) : cellContent(columns[0], row)}
                                    </span>
                                    <FontAwesomeIcon
                                        className="mobile-data-chevron"
                                        icon={(isExpanded ? ['fas', 'chevron-up'] : ['fas', 'chevron-down']) as IconProp}
                                        aria-hidden="true"
                                    />
                                </button>

                                {isExpanded && (
                                    <div className="mobile-data-details" id={detailsId}>
                                        {columns.filter((column) => !column.mobileHidden).map((column, columnIndex) => (
                                            <div className="mobile-data-detail-row" key={(column.id ?? String(columnIndex)) + '-mobile'}>
                                                <span className="mobile-data-detail-label">
                                                    {column.dataLabel ?? column.header}
                                                </span>
                                                <div className="mobile-data-detail-value">
                                                    {cellContent(column, row)}
                                                </div>
                                            </div>
                                        ))}

                                        {(mobileRowActionLabel || rowActions.length > 0) && (
                                            <div className="mobile-data-detail-row mobile-data-actions-row">
                                                <span className="mobile-data-detail-label">Actions</span>
                                                <div className="mobile-data-actions">
                                                    {mobileRowActionLabel && onRowClick && (
                                                        <button type="button" className="btn" onClick={() => onRowClick(row)}>
                                                            {mobileRowActionLabel}
                                                        </button>
                                                    )}
                                                    {rowActions.map((action, actionIndex) => (
                                                        <button
                                                            key={actionIndex}
                                                            type="button"
                                                            className={action.classes ?? 'btn'}
                                                            onClick={() => action.onClick(row)}
                                                        >
                                                            {action.text}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </article>
                        )
                    })
                )}
            </div>
        </div>
    )
}

export default DataTable
