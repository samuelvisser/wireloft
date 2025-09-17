import type {FieldValues, Path, UseFormSetError} from "react-hook-form";
import type {ServerErrorItem} from "./serverMessageMap";

function locToPath(loc?: (string | number)[]): string | null {
    if (!loc || !loc.length) return null;
    const start = typeof loc[0] === "string" && ["body", "query", "path"].includes(String(loc[0])) ? 1 : 0;
    const parts = loc.slice(start).map(String);
    return parts.length ? parts.join(".") : null; // supports nested: items.0.name
}

type ApplyOpts<TFieldValues extends FieldValues> = {
    mapMessage?: (err: ServerErrorItem, field: Path<TFieldValues>) => string | undefined;
    defaultMessage?: string;
};

export function applyFieldErrors<TFieldValues extends FieldValues>(
    payload: any,
    setError: UseFormSetError<TFieldValues>,
    fallbackField?: Path<TFieldValues>,
    opts?: ApplyOpts<TFieldValues>
): boolean {
    const items: ServerErrorItem[] = (Array.isArray(payload?.detail) && payload.detail) || [];

    if (!items.length) {
        if (typeof payload?.detail === "string") {
            setError(("root" as unknown) as Path<TFieldValues>, {type: "server", message: payload.detail});
            return true;
        }
        return false;
    }

    const prefix = "server:";
    for (const e of items) {
        const path = (locToPath(e.loc) as Path<TFieldValues>) || fallbackField || ("root" as Path<TFieldValues>);
        const field = typeof path === "string" ? path : "root";

        // Prefer your per-field override; else use server msg; else minimal default
        const override = opts?.mapMessage?.(e, field as Path<TFieldValues>);
        const message = override ?? e.msg ?? opts?.defaultMessage ?? "Invalid value";
        const errorType = e.type ? (prefix + e.type) : "server";

        setError(path, {type: errorType as any, message});
    }
    return true;
}
