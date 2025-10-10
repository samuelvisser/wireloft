export function getCurrentAppVersion(): string | undefined {
    try {
        return (window as any).publicConfig?.appVersion
    } catch {
        return undefined
    }
}

export async function getErrorMessageFromResponse(response: any): Promise<{ error: string, firstType: string }> {

    let errorMessage: string = "HTTP error"

    if (response.status) {
        errorMessage = `HTTP ${response.status}`
    }

    // Attempt to read server-provided error message
    try {
        const data = await response.json().catch(() => null as any)

        if (data.message) {
            const firstType = (typeof data.type === "string" && data.type) || "general";
            return {error: data.message, firstType};
        }

        if (data.detail) {
            let firstType = "unknown";

            const parts: string[] = data.detail.map((err: any, idx: number) => {
                const loc = Array.isArray(err?.loc) ? err.loc : [];
                const field = (typeof loc[1] === "string" && loc[1]) || "__all__";

                // Capture the first error type we see
                if (idx === 0 && typeof err?.type === "string") {
                    firstType = err.type;
                }

                const msg = typeof err?.msg === "string" ? err.msg : "Invalid value";

                // For request-level errors, don't prefix with a field name.
                if (field === "__all__") return msg;

                return `${field}: ${msg}`;
            });

            const error = parts.filter(Boolean).join("; ") || errorMessage;
            return {error, firstType};
        }
    } catch {
    }

    return {error: errorMessage, firstType: "unknown"};
}