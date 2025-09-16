export function getCurrentAppVersion(): string | undefined {
    try {
        return (window as any).appConfig?.APP_VERSION
    } catch {
        return undefined
    }
}