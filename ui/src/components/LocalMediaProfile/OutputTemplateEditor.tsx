import {useEffect, useMemo, useRef, useState, type ComponentProps, type CSSProperties, type ReactNode} from 'react'
import CodeMirror from '@uiw/react-codemirror'
import {
    autocompletion,
    pickedCompletion,
    startCompletion,
    type Completion,
    type CompletionContext,
} from '@codemirror/autocomplete'
import {indentUnit} from '@codemirror/language'
import {EditorView, type ViewUpdate} from '@codemirror/view'
import {Controller, type UseFormReturn, useWatch} from 'react-hook-form'

import ReadMore from '../../utils/ReadMore'
import {useLocalMediaProfilePreview, type LocalMediaProfilePreviewState} from '../../lib/localMediaProfilePreview'
import {
    type LocalMediaProfileTemplateSource,
    useLocalMediaProfileTemplateSources,
    useLocalMediaProfileTemplateVariables,
    useRandomShowTemplateSource,
} from '../../lib/localMediaProfileTemplateSources'
import type {LocalMediaProfileMode} from './LocalMediaProfileForm'
import TemplateSourceSelect from './TemplateSourceSelect'
import CustomIndexAdvisories from './CustomIndexAdvisories'
import {outputTemplateSyntaxExtensions} from './outputTemplateCodeMirror'
import {
    analyzeJinjaStatement,
    editorPositionForCompactOffset,
    getOpenJinjaBlocks,
    hasLeadingPathPartSpace,
    parseOutputTemplate,
    renderCompactOutputTemplate,
    renderEditorOutputTemplate,
    type JinjaBlockNode,
} from './outputTemplateFormatting'
import {getOutputTemplateVariables, type OutputTemplateVariable} from './outputTemplateVariables'
import './OutputTemplateEditor.css'
import './OutputTemplateEditorIde.css'

type Props = {
    form: UseFormReturn<any>
    mode: LocalMediaProfileMode
    placeholder: string
    help: ReactNode
    renderPreviewFields?: (preview: LocalMediaProfilePreviewState) => ReactNode
}

type TemplateCodeEditorProps = {
    value: string
    placeholder: string
    extensions: ComponentProps<typeof CodeMirror>['extensions']
    invalid: boolean
    onChange: (value: string) => void
    onBlur: () => void
}

type JinjaStatement = {
    label: string
    detail: string
    acceptsExpression?: boolean
}

const jinjaStatements: JinjaStatement[] = [
    {label: 'if', detail: 'Start a conditional block', acceptsExpression: true},
    {label: 'elif', detail: 'Add another conditional branch', acceptsExpression: true},
    {label: 'else', detail: 'Add a fallback branch'},
    {label: 'endif', detail: 'End a conditional block'},
    {label: 'for', detail: 'Start a loop', acceptsExpression: true},
    {label: 'endfor', detail: 'End a loop'},
    {label: 'set', detail: 'Assign a value', acceptsExpression: true},
    {label: 'endset', detail: 'End a block assignment'},
    {label: 'block', detail: 'Start a named block', acceptsExpression: true},
    {label: 'endblock', detail: 'End a named block'},
    {label: 'macro', detail: 'Define a macro', acceptsExpression: true},
    {label: 'endmacro', detail: 'End a macro'},
    {label: 'call', detail: 'Call a macro with a body', acceptsExpression: true},
    {label: 'endcall', detail: 'End a call block'},
    {label: 'filter', detail: 'Apply a filter to a block', acceptsExpression: true},
    {label: 'endfilter', detail: 'End a filter block'},
    {label: 'with', detail: 'Start a scoped block', acceptsExpression: true},
    {label: 'endwith', detail: 'End a scoped block'},
    {label: 'raw', detail: 'Start a raw Jinja block'},
    {label: 'endraw', detail: 'End a raw Jinja block'},
    {label: 'autoescape', detail: 'Start an autoescape block', acceptsExpression: true},
    {label: 'endautoescape', detail: 'End an autoescape block'},
]

function filterCompletion(label: string, detail: string, info: string): Completion {
    return {label, type: 'function', detail, info}
}

const wireloftFilterCompletionOptions: Completion[] = [
    filterCompletion(
        'strftime',
        'strftime(format)',
        'Format a WireLoft date or time value using Python strftime directives.',
    ),
    filterCompletion(
        'regex_replace',
        'regex_replace(pattern, replacement, count=0)',
        'Replace regex matches. count=0 replaces all matches.',
    ),
    filterCompletion(
        'regex_search',
        'regex_search(pattern)',
        'Return true when the regex matches anywhere in the value.',
    ),
    filterCompletion(
        'custom_index',
        "'key' | custom_index",
        'Use the current episode number from a defined Indexing Value.',
    ),
]

const jinjaNativeFilterCompletionOptions: Completion[] = [
    filterCompletion('abs', 'abs', 'Return the absolute value of a number.'),
    filterCompletion('attr', 'attr(name)', 'Get an attribute from an object.'),
    filterCompletion('batch', 'batch(linecount, fill_with=None)', 'Group items into rows with up to linecount items each.'),
    filterCompletion('capitalize', 'capitalize', 'Capitalize the first character and lowercase the rest.'),
    filterCompletion('center', 'center(width=80)', 'Center text in a field of the given width.'),
    filterCompletion('count', 'count', 'Return the number of items in a value.'),
    filterCompletion('d', "d(default_value='', boolean=False)", 'Alias for the default filter.'),
    filterCompletion('default', "default(default_value='', boolean=False)", 'Use a fallback when the value is undefined, or optionally false-like.'),
    filterCompletion('dictsort', "dictsort(case_sensitive=False, by='key', reverse=False)", 'Sort a dictionary and return key/value pairs.'),
    filterCompletion('e', 'e', 'Alias for the escape filter.'),
    filterCompletion('escape', 'escape', 'Escape HTML-special characters.'),
    filterCompletion('filesizeformat', 'filesizeformat(binary=False)', 'Format a number as a human-readable file size.'),
    filterCompletion('first', 'first', 'Return the first item in a sequence.'),
    filterCompletion('float', 'float(default=0.0)', 'Convert a value to a floating-point number.'),
    filterCompletion('forceescape', 'forceescape', 'Apply HTML escaping even to values already marked safe.'),
    filterCompletion('format', 'format(*args, **kwargs)', 'Apply printf-style formatting to a string.'),
    filterCompletion('groupby', 'groupby(attribute, default=None, case_sensitive=False)', 'Group items by an attribute.'),
    filterCompletion('indent', 'indent(width=4, first=False, blank=False)', 'Indent lines in a string.'),
    filterCompletion('int', 'int(default=0, base=10)', 'Convert a value to an integer.'),
    filterCompletion('items', 'items', 'Iterate over the key/value pairs in a mapping.'),
    filterCompletion('join', "join(d='', attribute=None)", 'Join items into a string, optionally using an attribute from each item.'),
    filterCompletion('last', 'last', 'Return the last item in a sequence.'),
    filterCompletion('length', 'length', 'Return the number of items in a value.'),
    filterCompletion('list', 'list', 'Convert a value to a list.'),
    filterCompletion('lower', 'lower', 'Convert text to lowercase.'),
    filterCompletion('map', 'map(*args, **kwargs)', 'Transform a sequence by applying a filter or reading an attribute.'),
    filterCompletion('max', 'max(case_sensitive=False, attribute=None)', 'Return the largest item in a sequence.'),
    filterCompletion('min', 'min(case_sensitive=False, attribute=None)', 'Return the smallest item in a sequence.'),
    filterCompletion('pprint', 'pprint', 'Format a value for debugging.'),
    filterCompletion('random', 'random', 'Return a random item from a sequence.'),
    filterCompletion('reject', 'reject(*args, **kwargs)', 'Keep sequence items that fail a Jinja test.'),
    filterCompletion('rejectattr', 'rejectattr(*args, **kwargs)', 'Keep items whose selected attribute fails a Jinja test.'),
    filterCompletion('replace', 'replace(old, new, count=None)', 'Replace occurrences of a substring.'),
    filterCompletion('reverse', 'reverse', 'Reverse text or iterate over a sequence in reverse.'),
    filterCompletion('round', "round(precision=0, method='common')", 'Round a number to the requested precision.'),
    filterCompletion('safe', 'safe', 'Mark a string as safe from HTML escaping.'),
    filterCompletion('select', 'select(*args, **kwargs)', 'Keep sequence items that pass a Jinja test.'),
    filterCompletion('selectattr', 'selectattr(*args, **kwargs)', 'Keep items whose selected attribute passes a Jinja test.'),
    filterCompletion('slice', 'slice(slices, fill_with=None)', 'Split a sequence into the requested number of slices.'),
    filterCompletion('sort', 'sort(reverse=False, case_sensitive=False, attribute=None)', 'Sort a sequence.'),
    filterCompletion('string', 'string', 'Convert a value to a string.'),
    filterCompletion('striptags', 'striptags', 'Remove SGML or XML tags and normalize adjacent whitespace.'),
    filterCompletion('sum', 'sum(attribute=None, start=0)', 'Add the values in a sequence.'),
    filterCompletion('title', 'title', 'Convert text to title case.'),
    filterCompletion('tojson', 'tojson(indent=None)', 'Serialize a value as JSON.'),
    filterCompletion('trim', 'trim(chars=None)', 'Remove leading and trailing characters, or whitespace by default.'),
    filterCompletion('truncate', "truncate(length=255, killwords=False, end='...', leeway=None)", 'Shorten text to a maximum length.'),
    filterCompletion('unique', 'unique(case_sensitive=False, attribute=None)', 'Return unique items from a sequence.'),
    filterCompletion('upper', 'upper', 'Convert text to uppercase.'),
    filterCompletion('urlencode', 'urlencode', 'Encode a value for use in a URL path or query.'),
    filterCompletion('urlize', 'urlize(trim_url_limit=None, nofollow=False, target=None, rel=None, extra_schemes=None)', 'Convert URLs in text to HTML links.'),
    filterCompletion('wordcount', 'wordcount', 'Count words in a string.'),
    filterCompletion('wordwrap', 'wordwrap(width=79, break_long_words=True, wrapstring=None, break_on_hyphens=True)', 'Wrap text to the requested width.'),
    filterCompletion('xmlattr', 'xmlattr(autospace=True)', 'Build an SGML/XML attribute string from a mapping.'),
]

type CompletionInfoRect = {
    top: number
    right: number
    bottom: number
    left: number
}

function positionCompletionInfo(list: CompletionInfoRect, info: CompletionInfoRect, space: CompletionInfoRect) {
    const gap = 4
    const infoWidth = info.right - info.left
    const infoHeight = info.bottom - info.top
    const rightSpace = space.right - list.right
    const leftSpace = list.left - space.left
    const canPlaceRight = rightSpace >= infoWidth + gap
    const canPlaceLeft = leftSpace >= infoWidth + gap

    if (canPlaceRight || canPlaceLeft) {
        const placeRight = canPlaceRight && (!canPlaceLeft || rightSpace >= leftSpace)
        return {
            style: `${placeRight ? 'left' : 'right'}: calc(100% + ${gap}px); top: 0`,
        }
    }

    const belowSpace = space.bottom - list.bottom
    const aboveSpace = list.top - space.top
    const placeBelow = belowSpace >= infoHeight + gap || belowSpace >= aboveSpace
    const maxWidth = Math.max(0, space.right - list.left)

    return {
        style: `${placeBelow ? 'top' : 'bottom'}: calc(100% + ${gap}px); left: 0; max-width: ${maxWidth}px`,
    }
}

function statementVariableExpression(statement: string): string | null {
    const keywordMatch = /^\s*([A-Za-z_][A-Za-z0-9_]*)\b/.exec(statement)
    if (!keywordMatch) return null

    const keyword = keywordMatch[1]
    const tail = statement.slice(keywordMatch[0].length)
    if (keyword === 'set') {
        const assignment = tail.indexOf('=')
        return assignment >= 0 ? tail.slice(assignment + 1) : null
    }
    if (keyword === 'for') {
        const iterable = /\bin\b/.exec(tail)
        return iterable ? tail.slice(iterable.index + iterable[0].length) : null
    }
    if (keyword === 'if' || keyword === 'elif' || keyword === 'call' || keyword === 'autoescape') {
        return tail
    }
    return null
}

function activeJinjaExpression(beforeCursor: string): string | null {
    const variableStart = beforeCursor.lastIndexOf('{{')
    const variableEnd = beforeCursor.lastIndexOf('}}')
    const statementStart = beforeCursor.lastIndexOf('{%')
    const statementEnd = beforeCursor.lastIndexOf('%}')

    if (variableStart > variableEnd && variableStart > statementStart) {
        return beforeCursor.slice(variableStart + 2)
    }
    if (statementStart <= statementEnd) return null
    return statementVariableExpression(beforeCursor.slice(statementStart + 2))
}

function isInsideQuotedString(source: string): boolean {
    let quote: "'" | '"' | null = null
    let escaped = false
    for (const character of source) {
        if (escaped) {
            escaped = false
            continue
        }
        if (character === '\\' && quote) {
            escaped = true
            continue
        }
        if (character === "'" || character === '"') {
            quote = quote === character ? null : (quote ?? character)
        }
    }
    return quote !== null
}

function replaceJinjaStatementCompletion(
    view: EditorView,
    completion: Completion,
    from: number,
    to: number,
    insert: string,
    anchorOffset = insert.length,
) {
    const statementStart = view.state.sliceDoc(0, from).lastIndexOf('{%')
    const replaceFrom = statementStart >= 0 ? statementStart + 2 : from
    const closingTag = /^\s*%}/.exec(view.state.sliceDoc(to))
    const replaceTo = closingTag ? to + closingTag[0].length : to
    view.dispatch({
        changes: {from: replaceFrom, to: replaceTo, insert},
        selection: {anchor: replaceFrom + anchorOffset},
        annotations: pickedCompletion.of(completion),
    })
}

function closingBlockCompletion(openBlocks: JinjaBlockNode[], count: number): Completion {
    const blocks = openBlocks.slice(openBlocks.length - count).reverse()
    const closers = blocks.map(({expectedCloser}) => expectedCloser)
    const label = closers.join(', ')
    const insert = closers
        .map((closer, index) => index === 0 ? ` ${closer} %}` : `{% ${closer} %}`)
        .join('')
    const blockLabels = blocks.map(({keyword}) => keyword).join(', ')

    return {
        label,
        type: 'keyword',
        detail: count === 1 ? `Close the ${blockLabels} block` : `Close ${blockLabels} blocks in order`,
        boost: 200 - count,
        apply: (view, completion, from, to) => {
            replaceJinjaStatementCompletion(view, completion, from, to, insert)
        },
    }
}

function structuralEdit(update: ViewUpdate): boolean {
    let structural = false
    update.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
        const added = inserted.toString()
        const removed = update.startState.doc.sliceString(fromA, toA)
        if (added.includes('\n') || added.includes('\r')) return
        if (
            added.includes('/')
            || added.includes('%}')
            || added.includes('}}')
            || added.includes('#}')
            || removed.includes('/')
            || removed.includes('%}')
            || removed.includes('}}')
            || removed.includes('#}')
        ) {
            structural = true
        }
    })
    return structural
}

function formatEditorAfterStructuralEdit(update: ViewUpdate) {
    if (!update.docChanged || !update.state.selection.main.empty || !structuralEdit(update)) return

    const original = update.state.doc.toString()
    const rendered = renderEditorOutputTemplate(parseOutputTemplate(original, 'editor'))
    if (rendered.value === original) return

    const cursor = update.state.selection.main.head
    const compactOffset = renderCompactOutputTemplate(
        parseOutputTemplate(original.slice(0, cursor), 'editor'),
    ).length
    queueMicrotask(() => {
        const view = update.view
        if (view.state.doc.toString() !== original) return
        const anchor = editorPositionForCompactOffset(rendered, compactOffset)
        view.dispatch({
            changes: {from: 0, to: view.state.doc.length, insert: rendered.value},
            selection: {anchor},
        })
    })
}

function indentAfterNewline(update: ViewUpdate) {
    if (!update.docChanged || !update.state.selection.main.empty) return

    let insertedNewline = false
    update.changes.iterChanges((_fromA, _toA, _fromB, _toB, inserted) => {
        if (inserted.toString().includes('\n')) insertedNewline = true
    })
    if (!insertedNewline) return

    const documentAfterEnter = update.state.doc.toString()
    queueMicrotask(() => {
        const view = update.view
        if (view.state.doc.toString() !== documentAfterEnter || !view.state.selection.main.empty) return

        const cursor = view.state.selection.main.head
        const line = view.state.doc.lineAt(cursor)
        if (line.number <= 1) return

        const previousLine = view.state.doc.line(line.number - 1)
        const previousIndent = previousLine.text.match(/^\t*/)?.[0] ?? ''
        const previousContent = previousLine.text.slice(previousIndent.length).trimEnd()
        const statement = previousContent.match(/{%\s*([A-Za-z_][A-Za-z0-9_]*)\b[^%]*(?:%})?\s*$/)
        const info = statement ? analyzeJinjaStatement(statement[0]) : undefined
        const definition = info ? jinjaStatements.find(({label}) => label === info.keyword) : undefined
        const incompleteKeywordNeedsSpace = !!info
            && !previousContent.includes('%}')
            && !!definition?.acceptsExpression
            && previousContent.trimEnd().endsWith(info.keyword)

        const desiredIndent = `${previousIndent}${info?.opensBlock || info?.isBranch ? '\t' : ''}${incompleteKeywordNeedsSpace ? ' ' : ''}`
        const currentIndent = line.text.match(/^[\t ]*/)?.[0] ?? ''
        if (cursor > line.from + currentIndent.length || currentIndent === desiredIndent) return

        view.dispatch({
            changes: {from: line.from, to: line.from + currentIndent.length, insert: desiredIndent},
            selection: {anchor: line.from + desiredIndent.length},
        })
    })
}

function TemplateCodeEditor({
                                value,
                                placeholder,
                                extensions,
                                invalid,
                                onChange,
                                onBlur,
                            }: TemplateCodeEditorProps) {
    const canonicalValue = value ?? ''
    const [editorValue, setEditorValue] = useState(() => (
        renderEditorOutputTemplate(parseOutputTemplate(canonicalValue, 'compact')).value
    ))
    const lastCanonicalValue = useRef(canonicalValue)

    useEffect(() => {
        if (canonicalValue === lastCanonicalValue.current) return
        lastCanonicalValue.current = canonicalValue
        setEditorValue(renderEditorOutputTemplate(parseOutputTemplate(canonicalValue, 'compact')).value)
    }, [canonicalValue])

    return (
        <CodeMirror
            id="mp-path"
            className="output-template-code-editor"
            value={editorValue}
            minHeight="96px"
            placeholder={placeholder}
            extensions={extensions}
            basicSetup={{
                lineNumbers: false,
                foldGutter: false,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
                autocompletion: false,
            }}
            onChange={(nextValue) => {
                setEditorValue(nextValue)
                const compactValue = renderCompactOutputTemplate(parseOutputTemplate(nextValue, 'editor'))
                lastCanonicalValue.current = compactValue
                onChange(compactValue)
            }}
            onBlur={() => {
                setEditorValue((current) => (
                    renderEditorOutputTemplate(parseOutputTemplate(current, 'editor')).value
                ))
                onBlur()
            }}
            aria-label="Output path template"
            aria-invalid={invalid}
            aria-describedby={invalid ? 'mp-path-error' : 'mp-path-help'}
        />
    )
}

function PreviewPathPart({part}: { part: string }) {
    const leadingSpaceCount = part.match(/^ +/)?.[0].length ?? 0
    return (
        <>
            {leadingSpaceCount > 0 && (
                <span
                    title={leadingSpaceCount === 1 ? 'Leading space' : `${leadingSpaceCount} leading spaces`}
                    aria-label={leadingSpaceCount === 1 ? 'leading space' : `${leadingSpaceCount} leading spaces`}
                >
                    {'␣'.repeat(leadingSpaceCount)}
                </span>
            )}
            {part.slice(leadingSpaceCount)}
        </>
    )
}

function PreviewLoadingIndicator() {
    return (
        <span
            className="template-preview-loading-indicator"
            role="status"
            aria-label="Loading example"
        >
            <span/>
            <span/>
            <span/>
        </span>
    )
}

function PreviewPath({path}: { path: string }) {
    const absolute = path.startsWith('/')
    const parts = path.split('/').filter(Boolean)
    if (!absolute || parts.length < 2) return <code>{path}</code>

    return (
        <code className="template-preview-path-tree" title={path}>
            {parts.map((part, index) => (
                <span
                    key={`${part}-${index}`}
                    className="template-preview-path-segment"
                    style={{'--template-path-depth': index} as CSSProperties}
                >
                    <span className="template-preview-path-branch" aria-hidden="true">{index === 0 ? '' : '└─ '}</span>
                    {index === 0 ? '/' : ''}<PreviewPathPart part={part}/>{index < parts.length - 1 ? '/' : ''}
                </span>
            ))}
        </code>
    )
}

export default function OutputTemplateEditor({form, mode, placeholder, help, renderPreviewFields}: Props) {
    const {control, formState: {errors}} = form
    const template = useWatch({control, name: 'outputTemplate'}) ?? ''
    const preferredFormat = useWatch({control, name: 'preferredFormat'}) ?? ''
    const showScope = useWatch({control, name: 'showScope'}) ?? 'both'
    const indexingValues = useWatch({control, name: 'indexingValues'}) ?? []
    const rawLocalMediaProfileId = useWatch({control, name: 'id'})
    const localMediaProfileId = typeof rawLocalMediaProfileId === 'number'
        ? rawLocalMediaProfileId
        : null
    const canonicalTemplate = useMemo(
        () => renderCompactOutputTemplate(parseOutputTemplate(template, 'compact')),
        [template],
    )
    const pathHasLeadingSpace = useMemo(
        () => hasLeadingPathPartSpace(parseOutputTemplate(canonicalTemplate, 'compact')),
        [canonicalTemplate],
    )

    useEffect(() => {
        if (canonicalTemplate === template) return
        form.setValue('outputTemplate', canonicalTemplate, {
            shouldDirty: false,
            shouldTouch: false,
            shouldValidate: false,
        })
    }, [canonicalTemplate, form, template])

    const [sourceSearch, setSourceSearch] = useState('')
    const [selectedSource, setSelectedSource] = useState<LocalMediaProfileTemplateSource | null>(null)
    const [testValues, setTestValues] = useState<Record<string, string>>({})
    const [testValuesExpanded, setTestValuesExpanded] = useState(false)
    const sourceQuery = useLocalMediaProfileTemplateSources(mode, {
        showScope,
        search: sourceSearch,
        anchorSourceId: selectedSource?.id,
    })
    const randomShowSourceQuery = useRandomShowTemplateSource(showScope, mode === 'show')
    const variableQuery = useLocalMediaProfileTemplateVariables(mode)
    const customVariables = (variableQuery.data ?? []) as OutputTemplateVariable[]
    const variables = useMemo(
        () => getOutputTemplateVariables(mode, customVariables),
        [customVariables, mode],
    )
    const [usedVariableNames, setUsedVariableNames] = useState<string[]>([])
    const [provisionalIndexingValueNames, setProvisionalIndexingValueNames] = useState<string[]>([])
    const usedVariables = useMemo(
        () => {
            const used = new Set(usedVariableNames)
            return variables.filter(({name}) => used.has(name))
        },
        [usedVariableNames, variables],
    )
    const usedVariablesKey = usedVariables.map(({name}) => name).join('|')
    const missingMetadataVariables = useMemo(() => {
        const prefix = mode === 'movie' ? 'meta_movie_' : 'meta_show_'
        const available = new Set(customVariables.map(({name}) => name))
        return [...new Set(
            usedVariableNames.filter((name) => name.startsWith(prefix) && !available.has(name)),
        )].sort()
    }, [customVariables, mode, usedVariableNames])

    const variableCompletionOptions = useMemo<Completion[]>(
        () => variables.map((variable) => ({
            label: variable.name,
            type: 'variable',
            detail: variable.description,
        })),
        [variables],
    )
    const printVariableCompletionOptions = useMemo<Completion[]>(
        () => variableCompletionOptions.map((option) => ({
            ...option,
            apply: (view, completion, from, to) => {
                const variableStart = view.state.sliceDoc(0, from).lastIndexOf('{{')
                const replaceFrom = variableStart >= 0 ? variableStart + 2 : from
                const closingBraces = /^\s*}}/.exec(view.state.sliceDoc(to))
                const replaceTo = closingBraces ? to + closingBraces[0].length : to
                const insert = ` ${completion.label} }}`
                view.dispatch({
                    changes: {from: replaceFrom, to: replaceTo, insert},
                    selection: {anchor: replaceFrom + insert.length},
                    annotations: pickedCompletion.of(completion),
                })
            },
        })),
        [variableCompletionOptions],
    )
    const statementCompletionOptions = useMemo<Completion[]>(
        () => jinjaStatements
            .filter(({label}) => !label.startsWith('end'))
            .map((statement) => ({
                label: statement.label,
                type: 'keyword',
                detail: statement.detail,
                apply: (view, completion, from, to) => {
                    const insert = ` ${statement.label}${statement.acceptsExpression ? '  ' : ' '}%}`
                    const anchorOffset = statement.acceptsExpression
                        ? ` ${statement.label} `.length
                        : insert.length
                    replaceJinjaStatementCompletion(view, completion, from, to, insert, anchorOffset)
                },
            })),
        [],
    )
    const editorExtensions = useMemo(() => {
        const filterCompletionSource = (context: CompletionContext) => {
            const beforeCursor = context.state.sliceDoc(0, context.pos)
            const expression = activeJinjaExpression(beforeCursor)
            if (expression === null) return null

            const filterMatch = /\|\s*([A-Za-z_][A-Za-z0-9_]*)?$/.exec(expression)
            if (!filterMatch) return null
            if (isInsideQuotedString(expression.slice(0, filterMatch.index))) return null

            const currentWord = filterMatch[1] ?? ''
            return {
                from: context.pos - currentWord.length,
                options: [
                    ...wireloftFilterCompletionOptions
                        .filter((option) => mode === 'show' || option.label !== 'custom_index')
                        .map((option) => currentWord ? option : {...option, boost: 99}),
                    ...jinjaNativeFilterCompletionOptions,
                ],
                validFor: /^(?:[A-Za-z_][A-Za-z0-9_]*)?$/,
            }
        }
        const variableCompletionSource = (context: CompletionContext) => {
            const beforeCursor = context.state.sliceDoc(0, context.pos)
            const variableStart = beforeCursor.lastIndexOf('{{')
            const variableEnd = beforeCursor.lastIndexOf('}}')
            const statementStart = beforeCursor.lastIndexOf('{%')
            const statementEnd = beforeCursor.lastIndexOf('%}')

            if (variableStart > variableEnd && variableStart > statementStart) {
                const expression = beforeCursor.slice(variableStart + 2)
                if (!/^\s*[A-Za-z_][A-Za-z0-9_]*$/.test(expression) && !/^\s*$/.test(expression)) return null
                const currentWord = expression.match(/[A-Za-z_][A-Za-z0-9_]*$/)?.[0] ?? ''

                return {
                    from: context.pos - currentWord.length,
                    options: printVariableCompletionOptions,
                    validFor: /^(?:[A-Za-z_][A-Za-z0-9_]*)?$/,
                }
            }

            if (statementStart <= statementEnd) return null
            const statement = beforeCursor.slice(statementStart + 2)
            const expression = statementVariableExpression(statement)
            if (expression === null) return null

            const currentWord = expression.match(/[A-Za-z_][A-Za-z0-9_]*$/)?.[0] ?? ''
            if (!currentWord && !context.explicit) return null
            const expressionBeforeWord = expression.slice(0, expression.length - currentWord.length)
            if (isInsideQuotedString(expressionBeforeWord)) return null

            const previousSignificantCharacter = expressionBeforeWord.trimEnd().slice(-1)
            if (previousSignificantCharacter === '.' || previousSignificantCharacter === '|') return null

            return {
                from: context.pos - currentWord.length,
                options: variableCompletionOptions,
                validFor: /^(?:[A-Za-z_][A-Za-z0-9_]*)?$/,
            }
        }
        const statementCompletionSource = (context: CompletionContext) => {
            const beforeCursor = context.state.sliceDoc(0, context.pos)
            const statementStart = beforeCursor.lastIndexOf('{%')
            const statementEnd = beforeCursor.lastIndexOf('%}')
            if (statementStart <= statementEnd) return null

            const statement = beforeCursor.slice(statementStart + 2)
            if (!/^\s*[A-Za-z_]*$/.test(statement)) return null
            const currentWord = statement.match(/[A-Za-z_]*$/)?.[0] ?? ''
            const openBlocks = getOpenJinjaBlocks(beforeCursor.slice(0, statementStart))
            const currentBlock = openBlocks[openBlocks.length - 1]
            const hasElse = currentBlock?.branches.some(({statement: branch}) => branch.keyword === 'else') ?? false
            const contextualOptions = openBlocks
                .map((_block, index) => closingBlockCompletion(openBlocks, index + 1))
            const generalOptions = statementCompletionOptions.filter(({label}) => {
                if (label === 'elif') return currentBlock?.keyword === 'if' && !hasElse
                if (label === 'else') {
                    return (currentBlock?.keyword === 'if' || currentBlock?.keyword === 'for') && !hasElse
                }
                return true
            })

            return {
                from: context.pos - currentWord.length,
                options: [...contextualOptions, ...generalOptions],
                validFor: /^[A-Za-z_]*$/,
            }
        }
        const openCompletionsAfterJinjaDelimiter = EditorView.updateListener.of((update) => {
            if (!update.docChanged || !update.state.selection.main.empty) return
            const cursor = update.state.selection.main.head
            if (cursor < 1) return

            const beforeCursor = update.state.doc.sliceString(0, cursor)
            const delimiter = cursor >= 2 ? beforeCursor.slice(-2) : ''
            const justTypedFilter = beforeCursor.endsWith('|') && activeJinjaExpression(beforeCursor) !== null
            if (delimiter === '{{' || delimiter === '{%' || justTypedFilter) {
                queueMicrotask(() => startCompletion(update.view))
            }
        })
        return [
            ...outputTemplateSyntaxExtensions,
            indentUnit.of('\t'),
            autocompletion({
                override: [filterCompletionSource, variableCompletionSource, statementCompletionSource],
                positionInfo: (_view, list, _option, info, space) => positionCompletionInfo(list, info, space),
            }),
            EditorView.lineWrapping,
            openCompletionsAfterJinjaDelimiter,
            EditorView.updateListener.of(indentAfterNewline),
            EditorView.updateListener.of(formatEditorAfterStructuralEdit),
            EditorView.theme({
                '&': {fontSize: '16px'},
                '.cm-content': {fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'},
            }),
        ]
    }, [mode, printVariableCompletionOptions, statementCompletionOptions, variableCompletionOptions])

    const sources = useMemo(() => {
        const byId = new Map<string, LocalMediaProfileTemplateSource>()
        for (const page of sourceQuery.data?.pages ?? []) {
            for (const source of page.items) {
                if (!byId.has(source.id)) byId.set(source.id, source)
            }
        }
        return [...byId.values()]
    }, [sourceQuery.data])
    useEffect(() => {
        setSelectedSource(null)
        setTestValues({})
        setSourceSearch('')
    }, [mode, showScope])

    useEffect(() => {
        if (selectedSource) return
        if (mode === 'show') {
            if (randomShowSourceQuery.isLoading) return
            if (randomShowSourceQuery.data) {
                setSelectedSource(randomShowSourceQuery.data)
                setTestValues({...randomShowSourceQuery.data.values})
                return
            }
        }
        if (!sources.length) return
        setSelectedSource(sources[0])
        setTestValues({...sources[0].values})
    }, [
        mode,
        randomShowSourceQuery.data,
        randomShowSourceQuery.isLoading,
        selectedSource,
        sources,
    ])

    useEffect(() => {
        setTestValues((current) => {
            const next = {...current}
            let changed = false
            for (const {name} of usedVariables) {
                if (!(name in next)) {
                    next[name] = selectedSource?.values[name] ?? ''
                    changed = true
                }
            }
            return changed ? next : current
        })
    }, [selectedSource, usedVariablesKey])

    const preview = useLocalMediaProfilePreview(template && selectedSource ? {
        type: mode,
        outputTemplate: template,
        preferredFormat,
        values: testValues,
        sourceId: selectedSource.id,
        localMediaProfileId: mode === 'show' ? localMediaProfileId : null,
        indexingValues: mode === 'show' ? indexingValues : null,
    } : null)
    const previewPath = preview.result?.output.outputPath ?? ''
    const previewError = preview.error || preview.result?.output.error || ''
    const previewLoading = preview.loading
    const previewIndicatorLoading = selectedSource
        ? previewLoading
        : sourceQuery.isLoading || (mode === 'show' && randomShowSourceQuery.isLoading)

    useEffect(() => {
        // Keep editable controls mounted while the shared request is pending.
        if (preview.loading) return
        const output = preview.result?.output
        setUsedVariableNames(output?.usedVariables ?? [])
        setProvisionalIndexingValueNames(output?.provisionalIndexingValues ?? [])
    }, [preview.loading, preview.result])

    function chooseSource(source: LocalMediaProfileTemplateSource) {
        setSelectedSource(source)
        setTestValues({...source.values})
    }

    return (
        <>
            {renderPreviewFields?.(preview)}
            <div className="form-row output-template-field">
                <section className="template-workbench" aria-labelledby="template-editor-heading">
                    <div className="template-editor-heading">
                        <div>
                            <label id="template-editor-heading" htmlFor="mp-path">Output path template</label>
                            <p>Type <code>{'{{'}</code> for variables or <code>{'{%'}</code> for Jinja statements.</p>
                        </div>
                        <span className="template-language-badge">Jinja</span>
                    </div>
                    <Controller
                        control={control}
                        name="outputTemplate"
                        render={({field}) => (
                            <TemplateCodeEditor
                                value={field.value ?? ''}
                                placeholder={placeholder}
                                extensions={editorExtensions}
                                invalid={!!errors.outputTemplate}
                                onChange={(value) => {
                                    field.onChange(value)
                                    form.clearErrors('outputTemplate')
                                }}
                                onBlur={field.onBlur}
                            />
                        )}
                    />
                    {errors.outputTemplate && (
                        <div id="mp-path-error" className="error" role="alert" aria-live="polite">
                            {String(errors.outputTemplate.message)}
                        </div>
                    )}
                    {variableQuery.isError && (
                        <div className="error" role="alert">
                            Custom metadata fields could not be loaded. Try refreshing the page.
                        </div>
                    )}
                    {missingMetadataVariables.length > 0 && (
                        <div className="template-metadata-warning" role="status">
                            {missingMetadataVariables.length === 1 ? 'Custom metadata field ' : 'Custom metadata fields '}
                            {missingMetadataVariables.map((name, index) => (
                                <span key={name}>
                                {index > 0 ? ', ' : ''}<code>{`{{\u00a0${name}\u00a0}}`}</code>
                            </span>
                            ))}
                            {missingMetadataVariables.length === 1 ? ' does' : ' do'} not exist yet and will render as empty.
                        </div>
                    )}
                    {mode === 'show' && (
                        <CustomIndexAdvisories
                            template={template}
                            indexingValues={indexingValues}
                            onApply={(value) => {
                                form.clearErrors('outputTemplate')
                                form.setValue('outputTemplate', value, {
                                    shouldDirty: true,
                                    shouldTouch: true,
                                    shouldValidate: true,
                                })
                            }}
                        />
                    )}
                    {provisionalIndexingValueNames.length > 0 && (
                        <div className="template-preview-status" role="status">
                            {provisionalIndexingValueNames.length === 1 ? 'Indexing Value ' : 'Indexing Values '}
                            {provisionalIndexingValueNames.map((name, index) => (
                                <span key={name}>
                                {index > 0 ? ', ' : ''}<code>{name}</code>
                            </span>
                            ))}
                            {provisionalIndexingValueNames.length === 1 ? ' is' : ' are'} simulated from the current draft. Previewing does not save
                            an assignment.
                        </div>
                    )}
                    {pathHasLeadingSpace && (
                        <div className="template-metadata-warning" role="status">
                            One or more path parts begins with a space. This is usually not intentional.
                        </div>
                    )}

                    <div className="template-workbench-divider"/>
                    <div className="template-preview-area">
                        <div className="template-playground-heading">
                            <div>
                                <h3 id="template-preview-heading">Example output</h3>
                                <p>Try different values here. Your profile is not changed.</p>
                            </div>
                            <label className="template-source-label" htmlFor="template-example-source">
                                <span>Example source</span>
                                <TemplateSourceSelect
                                    mode={mode}
                                    sources={sources}
                                    selectedSource={selectedSource}
                                    isLoading={
                                        sourceQuery.isLoading
                                        || sourceQuery.isFetchingNextPage
                                        || sourceQuery.isFetchingPreviousPage
                                        || (mode === 'show' && !selectedSource && randomShowSourceQuery.isLoading)
                                    }
                                    hasMore={sourceQuery.hasNextPage ?? false}
                                    hasPrevious={sourceQuery.hasPreviousPage ?? false}
                                    onChange={chooseSource}
                                    onSearchChange={setSourceSearch}
                                    onLoadMore={() => void sourceQuery.fetchNextPage()}
                                    onLoadPrevious={() => void sourceQuery.fetchPreviousPage()}
                                />
                            </label>
                        </div>

                        {preview.simulatingCustomIndexes && (
                            <span className="template-preview-status">
                                <strong>Calculating simulated Custom Index…</strong>{' '}
                                This preview needs to recalculate index assignments and may take longer than normal.
                            </span>
                        )}
                        {sourceQuery.isError && (
                            <p className="error" role="alert">Examples could not be loaded. Try refreshing the page.</p>
                        )}
                        {selectedSource?.fallback && (
                            <p className="template-preview-status">No {mode === 'movie' ? 'movies' : 'episodes'} found yet, so example values are
                                being used.</p>
                        )}

                        <div className={`template-preview-output${previewError ? ' has-error' : ''}`} aria-live="polite">
                            <span className="template-preview-output-label">Path</span>
                            {previewIndicatorLoading && <PreviewLoadingIndicator/>}

                            {!selectedSource && sourceQuery.isLoading
                                ? <code>Loading example source</code>
                                : previewError
                                    ? <span className="error">{previewError}</span>
                                    : previewPath
                                        ? <PreviewPath path={previewPath}/>
                                        : <code>{previewLoading ? 'Rendering…' : 'Add a variable to preview this path.'}</code>
                            }
                        </div>

                        <div className="template-test-values">
                            {!testValuesExpanded && (
                                <>
                                    <span className="template-preview-live-note">Preview updates as you type</span>
                                    <button
                                        type="button"
                                        className="btn btn-small template-test-values-toggle"
                                        aria-expanded={false}
                                        aria-controls="template-test-values-fields"
                                        onClick={() => setTestValuesExpanded(true)}
                                    >
                                        Test different values
                                    </button>
                                </>
                            )}
                            {testValuesExpanded && (
                                <div id="template-test-values-fields" className="template-test-values-content">
                                    <div className="template-test-values-heading">
                                        <h4>Test values</h4>
                                        <div className="template-test-values-actions">
                                            {selectedSource && usedVariables.length > 0 && (
                                                <button
                                                    type="button"
                                                    className="btn btn-small"
                                                    onClick={() => setTestValues({...selectedSource.values})}
                                                >
                                                    Reset values
                                                </button>
                                            )}
                                            <button
                                                type="button"
                                                className="btn btn-small"
                                                aria-expanded={true}
                                                aria-controls="template-test-values-fields"
                                                onClick={() => setTestValuesExpanded(false)}
                                            >
                                                Hide test values
                                            </button>
                                        </div>
                                    </div>
                                    {usedVariables.length === 0 ? (
                                        <p className="template-preview-status">Variables you add to the template will appear here automatically.</p>
                                    ) : (
                                        <div className="template-test-values-grid">
                                            {usedVariables.map((variable) => (
                                                <label key={variable.name}>
                                                    <span><code>{`{{\u00a0${variable.name}\u00a0}}`}</code> <small>{variable.description}</small></span>
                                                    <input
                                                        className="input"
                                                        type="text"
                                                        value={testValues[variable.name] ?? ''}
                                                        onChange={(event) => setTestValues((current) => ({
                                                            ...current,
                                                            [variable.name]: event.target.value,
                                                        }))}
                                                    />
                                                </label>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </section>

                <div className="help output-template-help" id="mp-path-help">
                    <ReadMore summary="Jinja syntax and all available variables.">
                        <div className="output-template-guidance">{help}</div>
                        <h4>Available variables</h4>
                        <dl className="output-template-variable-reference">
                            {variables.map((variable) => (
                                <div key={variable.name}>
                                    <dt><code>{`{{ ${variable.name} }}`}</code></dt>
                                    <dd>
                                        {variable.readMore ? (
                                            <ReadMore summary={variable.readMore.summary ?? variable.description}>
                                                {variable.readMore.paragraphs.map((paragraph) => (
                                                    <p
                                                        key={paragraph}
                                                        dangerouslySetInnerHTML={{__html: paragraph}}
                                                    />
                                                ))}
                                            </ReadMore>
                                        ) : variable.description}
                                    </dd>
                                </div>
                            ))}
                        </dl>
                    </ReadMore>
                </div>
            </div>
        </>
    )
}
