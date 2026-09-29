import CodeMirror from '@uiw/react-codemirror'
import {EditorView} from '@codemirror/view'

import {outputTemplateSyntaxExtensions} from './outputTemplateCodeMirror'
import {
    parseOutputTemplate,
    renderCompactOutputTemplate,
    renderEditorOutputTemplate,
    type OutputTemplateSourceMode,
} from './outputTemplateFormatting'
import './OutputTemplateEditor.css'
import './ReadOnlyOutputTemplateCode.css'

export type OutputTemplateRenderMode = 'compact' | 'editor'

export type ReadOnlyOutputTemplateCodeProps = {
    source: string
    label: string
    sourceMode?: OutputTemplateSourceMode
    renderMode?: OutputTemplateRenderMode
    className?: string
}

const readOnlyCodeExtensions = [
    ...outputTemplateSyntaxExtensions,
    EditorView.lineWrapping,
]

export default function ReadOnlyOutputTemplateCode({
    source,
    label,
    sourceMode = 'editor',
    renderMode = 'editor',
    className,
}: ReadOnlyOutputTemplateCodeProps) {
    const ast = parseOutputTemplate(source, sourceMode)
    const value = renderMode === 'compact'
        ? renderCompactOutputTemplate(ast)
        : renderEditorOutputTemplate(ast).value

    return (
        <CodeMirror
            className={`output-template-code-editor read-only-output-template-code-editor${className ? ` ${className}` : ''}`}
            value={value}
            editable={false}
            extensions={readOnlyCodeExtensions}
            basicSetup={{
                lineNumbers: false,
                foldGutter: false,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
                autocompletion: false,
            }}
            aria-label={label}
        />
    )
}
