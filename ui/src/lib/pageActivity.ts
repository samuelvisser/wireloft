import {useSyncExternalStore} from 'react'

function isPageActive(): boolean {
  return document.visibilityState === 'visible' && document.hasFocus()
}

function subscribeToPageActivity(onChange: () => void) {
  window.addEventListener('focus', onChange)
  window.addEventListener('blur', onChange)
  document.addEventListener('visibilitychange', onChange)

  return () => {
    window.removeEventListener('focus', onChange)
    window.removeEventListener('blur', onChange)
    document.removeEventListener('visibilitychange', onChange)
  }
}

export function usePageActive(): boolean {
  return useSyncExternalStore(subscribeToPageActivity, isPageActive, () => false)
}
