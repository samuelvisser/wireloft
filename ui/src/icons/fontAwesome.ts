import {library} from '@fortawesome/fontawesome-svg-core'
import {icons, proIcons} from 'virtual:font-awesome-registry'

library.add(...icons)

export const fontAwesomeIconMode = proIcons ? 'pro' : 'free'
