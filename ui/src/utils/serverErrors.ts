import type {FieldValues, Path, UseFormSetError} from "react-hook-form";
import type {ServerErrorItem} from "./serverMessageMap";

function locToPath(loc?: (string | number)[]): string | null {
    if (!loc || !loc.length) return null;
    const start = typeof loc[0] === "string" && ["body", "query", "path"].includes(String(loc[0])) ? 1 : 0;
    const parts = loc.slice(start).map(String);
    return parts.length ? parts.join(".") : null; // supports nested: items.0.name
}

type FieldOpts = {
    mapMessage?: (err: ServerErrorItem, fieldName: string) => string | undefined;
    defaultMessage?: string;
    fieldAlias?: Record<string, string>;
};

export function applyFieldErrors<TFieldValues extends FieldValues>(
    payload: any,
    setError: UseFormSetError<TFieldValues>,
    fallbackField?: Path<TFieldValues>,
    opts?: FieldOpts
): boolean {
    const errorItems: ServerErrorItem[] = (Array.isArray(payload?.detail) && payload.detail) || [];

    if (!errorItems.length) {
        if (typeof payload?.detail === "string") {
            setError(("root" as unknown) as Path<TFieldValues>, {type: "server", message: payload.detail});
            return true;
        }
        return false;
    }

    const prefix = "server:";
    for (const serverError of errorItems) {
        // 1) Determine the *source* field from loc/fallback
        const fieldPath = (locToPath(serverError.loc) as Path<TFieldValues>) || fallbackField || ("root" as Path<TFieldValues>);
        const fieldName = typeof fieldPath === "string" ? fieldPath : "root";

        // Field to display error on (resolve alias if needed)
        const routedField = (opts?.fieldAlias?.[fieldName] ?? fieldName) as Path<TFieldValues>;

        // Resolve message using the **source field** (not the routed one)
        const override = opts?.mapMessage?.(serverError, fieldName as Path<TFieldValues>);
        const message = override ?? serverError.msg ?? opts?.defaultMessage ?? "Invalid value";
        const errorType = serverError.type ? (prefix + serverError.type) : "server";

        setError(routedField, {type: errorType as any, message});
    }
    return true;
}
