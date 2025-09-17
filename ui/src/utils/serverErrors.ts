import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

type FastAPIErrorItem = {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
};

type FastAPIErrorPayload =
  | { detail?: FastAPIErrorItem[] }
  | { detail?: string }                                            // sometimes a simple string
  | Record<string, unknown>;

type NormalizedError = { path: string; message: string; type?: string };

function locToPath(loc?: (string | number)[]): string | null {
  if (!loc || !loc.length) return null;

  // FastAPI usually starts with "body" | "query" | "path", which RHF doesn't need.
  const start = typeof loc[0] === "string" && ["body", "query", "path"].includes(loc[0] as string) ? 1 : 0;
  const parts = loc.slice(start).map(String);
  if (!parts.length) return null;
  return parts.join("."); // e.g., items.0.name
}

export function normalizeFastAPIErrors(payload: FastAPIErrorPayload): NormalizedError[] {
  const items: FastAPIErrorItem[] = (Array.isArray((payload as any).detail) && (payload as any).detail) || [];

  if (Array.isArray(items) && items.length) {
    return items
      .map((e) => {
        const path = locToPath(e.loc);
        if (!path) return null;
        return { path, message: e.msg || "Invalid value", type: e.type };
      })
      .filter(Boolean) as NormalizedError[];
  }

  // Fallback: if backend returned { detail: "..." }
  if (typeof (payload as any).detail === "string") {
    return [{ path: "_root", message: String((payload as any).detail) }];
  }

  return [];
}

export function applyFieldErrors<TFieldValues extends FieldValues>(
  payload: FastAPIErrorPayload,
  setError: UseFormSetError<TFieldValues>,
  fallbackField?: Path<TFieldValues>
): boolean {
  const norm = normalizeFastAPIErrors(payload);
  if (!norm.length) return false;

  for (const e of norm) {
    const path = (e.path as Path<TFieldValues>) || fallbackField || ("_root" as Path<TFieldValues>);
    setError(path, { type: (e.type as any) || "server", message: e.message });
  }
  return true;
}
