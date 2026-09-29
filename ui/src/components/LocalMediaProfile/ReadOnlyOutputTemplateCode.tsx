import CodeMirror from '@uiw/react-codemirror'
import {EditorView} from '@codemirror/view'

import {outputTemplateSyntaxExtensions} from './outputTemplateCodeMirror'
import {parseOutputTemplate, renderEditorOutputTemplate} from './outputTemplateFormatting'
import './OutputTemplateEditor.css'
import './ReadOnlyOutputTemplateCode.css'

type Props = {
    source: string
    label: string
    sourceMode?: 'compact' | 'editor'
}

const readOnlyCodeExtensions = [
    ...outputTemplateSyntaxExtensions,
    EditorView.lineWrapping,
]

export default function ReadOnlyOutputTemplateCode({
    source,
    label,
    sourceMode = 'editor',
}: Props) {
    const value = renderEditorOutputTemplate(parseOutputTemplate(source, sourceMode)).value

    return (
        <CodeMirror
            className="output-template-code-editor read-only-output-template-code-editor"
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
