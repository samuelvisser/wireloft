import {useEffect, useMemo, useRef, useState, type ComponentProps, type CSSProperties, type ReactNode} from 'react'
import CodeMirror from '@uiw/react-codemirror'
import {
    autocompletion,
    pickedCompletion,
    startCompletion,
    type Completion,
    type CompletionContext,
} from '@codemirror/autocomplete'
import {indentUnit, HighlightStyle, syntaxHighlighting} from '@codemirror/language'
import {jinja} from '@codemirror/lang-jinja'
import {EditorView, type ViewUpdate} from '@codemirror/view'
import {tags} from '@lezer/highlight'
import {Controller, type UseFormReturn, useWatch} from 'react-hook-form'

import ReadMore from '../../utils/ReadMore'
import {
    type LocalMediaProfileTemplateSource,
    useLocalMediaProfileTemplateSources,
    useLocalMediaProfileTemplateVariables,
} from '../../lib/localMediaProfileTemplateSources'
import type {LocalMediaProfileMode} from './LocalMediaProfileForm'
import TemplateSourceSelect from './TemplateSourceSelect'
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

type TemplatePreviewResponse = {
    outputPath: string
    usedVariables: string[]
}

type Props = {
    form: UseFormReturn<any>
    mode: LocalMediaProfileMode
    placeholder: string
    help: ReactNode
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

const jinjaFilterCompletionOptions: Completion[] = [
    {
        label: 'regex_replace',
        type: 'function',
        detail: 'regex_replace(pattern, replacement, count=0)',
        info: 'Replace regex matches. count=0 replaces all matches.',
    },
    {
        label: 'regex_search',
        type: 'function',
        detail: 'regex_search(pattern)',
        info: 'Return true when the regex matches anywhere in the value.',
    },
]

const jinjaHighlightStyle = HighlightStyle.define([
    {tag: tags.brace, class: 'cm-jinja-brace'},
    {
        tag: [tags.keyword, tags.controlKeyword, tags.definitionKeyword, tags.operatorKeyword],
        class: 'cm-jinja-keyword',
    },
    {
        tag: [tags.variableName, tags.propertyName, tags.special(tags.variableName)],
        class: 'cm-jinja-variable',
    },
    {tag: tags.string, class: 'cm-jinja-string'},
    {tag: [tags.number, tags.bool], class: 'cm-jinja-literal'},
    {
        tag: [tags.operator, tags.arithmeticOperator, tags.logicOperator, tags.compareOperator],
        class: 'cm-jinja-operator',
    },
    {tag: tags.comment, class: 'cm-jinja-comment'},
    {tag: tags.blockComment, class: 'cm-jinja-comment'},
])

function responseErrorMessage(payload: any): string {
    const detail = payload?.detail
    if (Array.isArray(detail) && detail.length) return detail[0]?.msg ?? 'The template could not be rendered.'
    if (typeof detail === 'string') return detail
    return 'The template could not be rendered.'
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

function PreviewPathPart({part}: {part: string}) {
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

function PreviewPath({path}: {path: string}) {
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

export default function OutputTemplateEditor({form, mode, placeholder, help}: Props) {
    const {control, formState: {errors}} = form
    const template = useWatch({control, name: 'outputTemplate'}) ?? ''
    const preferredFormat = useWatch({control, name: 'preferredFormat'}) ?? ''
    const showScope = useWatch({control, name: 'showScope'}) ?? 'both'
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
    const sourceQuery = useLocalMediaProfileTemplateSources(mode, {
        showScope,
        search: sourceSearch,
    })
    const variableQuery = useLocalMediaProfileTemplateVariables(mode)
    const customVariables = (variableQuery.data ?? []) as OutputTemplateVariable[]
    const variables = useMemo(
        () => getOutputTemplateVariables(mode, customVariables),
        [customVariables, mode],
    )
    const [usedVariableNames, setUsedVariableNames] = useState<string[]>([])
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
                options: jinjaFilterCompletionOptions,
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
            jinja(),
            indentUnit.of('\t'),
            autocompletion({override: [filterCompletionSource, variableCompletionSource, statementCompletionSource]}),
            syntaxHighlighting(jinjaHighlightStyle),
            EditorView.lineWrapping,
            openCompletionsAfterJinjaDelimiter,
            EditorView.updateListener.of(indentAfterNewline),
            EditorView.updateListener.of(formatEditorAfterStructuralEdit),
            EditorView.theme({
                '&': {fontSize: '16px'},
                '.cm-content': {fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'},
            }),
        ]
    }, [printVariableCompletionOptions, statementCompletionOptions, variableCompletionOptions])

    const sources = useMemo(
        () => sourceQuery.data?.pages.flatMap((page) => page.items) ?? [],
        [sourceQuery.data],
    )
    const [selectedSource, setSelectedSource] = useState<LocalMediaProfileTemplateSource | null>(null)
    const [testValues, setTestValues] = useState<Record<string, string>>({})
    const [testValuesExpanded, setTestValuesExpanded] = useState(false)

    useEffect(() => {
        setSelectedSource(null)
        setTestValues({})
        setSourceSearch('')
    }, [mode, showScope])

    useEffect(() => {
        if (selectedSource || !sources.length) return
        setSelectedSource(sources[0])
        setTestValues({...sources[0].values})
    }, [selectedSource, sources])

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

    const [previewPath, setPreviewPath] = useState('')
    const [previewError, setPreviewError] = useState('')
    const [previewLoading, setPreviewLoading] = useState(false)
    const previewValuesKey = JSON.stringify(testValues)
    useEffect(() => {
        if (!template) {
            setUsedVariableNames([])
            setPreviewPath('')
            setPreviewError('')
            return
        }
        if (!selectedSource) return
        const controller = new AbortController()
        const timer = window.setTimeout(async () => {
            setPreviewLoading(true)
            try {
                const response = await fetch(
                    `${(window as any).appConfig.API_URL}/local-media-profiles/template/preview`,
                    {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        credentials: 'include',
                        signal: controller.signal,
                        body: JSON.stringify({
                            type: mode,
                            outputTemplate: template,
                            preferredFormat,
                            values: testValues,
                        }),
                    },
                )
                const payload = await response.json()
                if (!response.ok) {
                    setUsedVariableNames([])
                    setPreviewError(responseErrorMessage(payload))
                    return
                }
                const result = payload as TemplatePreviewResponse
                setPreviewPath(result.outputPath)
                setUsedVariableNames(result.usedVariables)
                setPreviewError('')
            } catch (error) {
                if ((error as Error).name !== 'AbortError') {
                    setUsedVariableNames([])
                    setPreviewError('The preview is temporarily unavailable.')
                }
            } finally {
                if (!controller.signal.aborted) setPreviewLoading(false)
            }
        }, 300)
        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
    }, [mode, preferredFormat, previewValuesKey, selectedSource, template])

    function chooseSource(source: LocalMediaProfileTemplateSource) {
        setSelectedSource(source)
        setTestValues({...source.values})
    }

    return (
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
                                isLoading={sourceQuery.isLoading || sourceQuery.isFetchingNextPage}
                                hasMore={sourceQuery.hasNextPage ?? false}
                                onChange={chooseSource}
                                onSearchChange={setSourceSearch}
                                onLoadMore={() => void sourceQuery.fetchNextPage()}
                            />
                        </label>
                    </div>

                    {sourceQuery.isLoading && <p className="template-preview-status">Loading an example…</p>}
                    {sourceQuery.isError && (
                        <p className="error" role="alert">Examples could not be loaded. Try refreshing the page.</p>
                    )}
                    {selectedSource?.fallback && (
                        <p className="template-preview-status">No {mode === 'movie' ? 'movies' : 'episodes'} found yet, so example values are being used.</p>
                    )}

                    <div className={`template-preview-output${previewError ? ' has-error' : ''}`} aria-live="polite">
                        <span className="template-preview-output-label">Path</span>
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
    )
}
