import ReadOnlyOutputTemplateCode, {
    type ReadOnlyOutputTemplateCodeProps,
} from './ReadOnlyOutputTemplateCode'
import './OpaqueOutputTemplateCode.css'

type Props = ReadOnlyOutputTemplateCodeProps

export default function OpaqueOutputTemplateCode({className, ...props}: Props) {
    const classes = ['opaque-output-template-code-editor', className]
        .filter(Boolean)
        .join(' ')

    return <ReadOnlyOutputTemplateCode {...props} className={classes}/>
}
