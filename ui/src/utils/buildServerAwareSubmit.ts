import type {UseFormReturn, FieldValues, Path} from "react-hook-form";
import {applyFieldErrors} from "./serverErrors";
import type {ServerErrorItem} from "./serverMessageMap";

type SubmitFn<TOut> = (data: TOut) => Promise<Response | void>;

// internal constants/helpers
const SERVER_PREFIX = "server:" as const;
const INIT_FLAG: unique symbol = Symbol("serverErrorAutoClearInit");

export type ServerAwareSubmitOptions<TIn extends FieldValues, TSuccess = unknown> = {
    onSuccess?: (result: TSuccess, ctx: {
        form: UseFormReturn<TIn>;
        response: Response;
        resetForm: (values?: Partial<TIn>) => void;
    }) => void | Promise<void>;

    /** HTTP statuses considered successful */
    successStatuses?: number[];

    /** Parse success payload. Return anything you want to receive in onSuccess. */
    parseSuccess?: (res: Response) => Promise<TSuccess>;

    /** If server error lacks a field path, map to this field; else to root */
    fallbackField?: Path<TIn>;

    /** Message used for unmapped server errors */
    genericMessage?: string;

    /** Override server error message for a specific field */
    mapMessage?: (err: ServerErrorItem, field: string) => string | undefined;

    /** Move errors for these fields under another field (e.g. { slug: "name" }) */
    fieldAlias?: Record<string, string>;

    /** List of server field names that should be routed to the fallbackField (if set) */
    aliasToFallback?: Path<TIn>[];

    /** Set a root-level summary when any field returns an error */
    rootOnFieldErrors?: boolean;                    // default: true

    /** Message to show at root for server-side validation errors */
    rootServerValidationMessage?: string;           // default: "Please fix the highlighted fields."

    /** Message to show at root for client-side invalid submits */
    rootClientValidationMessage?: string;           // default: "Please fix the highlighted fields."

    /** Clears the root banner when any field is changed */
    clearRootOnAnyChange?: boolean;                 // default true
};

function ensureAutoClearSubscription<TIn extends FieldValues>(
    form: UseFormReturn<TIn>,
    clearRootOnAnyChange: boolean
) {
    const f = form as any;
    if (f[INIT_FLAG]) return; // already installed

    const {watch, clearErrors} = form;

    const sub = watch((_, info) => {
        const fieldName = info?.name as Path<TIn> | undefined;
        if (!fieldName) return;

        // If the edited field currently has a server-tagged error, clear it.
        const fieldState = form.getFieldState(fieldName as any);
        const err = (fieldState as any)?.error;
        if (err?.type && (String(err.type) === 'server' || String(err.type).startsWith(SERVER_PREFIX))) {
            clearErrors(fieldName);
        }

        // Optionally clear root banner as user starts editing
        if (clearRootOnAnyChange) {
            clearErrors("root" as Path<TIn>);
        }
    });

    f[INIT_FLAG] = {unsubscribe: () => sub.unsubscribe()};
}

function focusFirstError<TIn extends FieldValues>(form: UseFormReturn<TIn>) {
    try {
        const firstKey = Object.keys((form as any).formState.errors || {}).find(k => k !== "root");
        if (firstKey) form.setFocus(firstKey as Path<TIn>);
    } catch {
    }
}

export function buildServerAwareSubmit<TIn extends FieldValues, TOut extends FieldValues = TIn, TSuccess = unknown>(
    form: UseFormReturn<TIn>,
    submitFn: SubmitFn<TOut>,
    options?: ServerAwareSubmitOptions<TIn, TSuccess>
) {
    const {handleSubmit, setError, reset, clearErrors} = form;

    const successStatuses = options?.successStatuses ?? [200, 201, 204];
    const parseSuccess = options?.parseSuccess ?? (async (res: Response) => {
        // Attempt JSON; if no body (204) or invalid JSON, return undefined
        if (res.status === 204) return undefined as unknown as TSuccess;
        const text = await res.text();
        if (!text) return undefined as unknown as TSuccess;
        try {
            return JSON.parse(text) as TSuccess;
        } catch {
            return undefined as unknown as TSuccess;
        }
    });

    const fallbackField = options?.fallbackField;
    const genericMessage = options?.genericMessage ?? "Something went wrong";
    const mapMessage = options?.mapMessage;
    const fieldAlias = options?.fieldAlias;
    const aliasToFallback = options?.aliasToFallback;

    // Merge explicit aliases with auto-aliases to fallbackField (if provided)
    const computedFieldAlias: Record<string, string> | undefined = (() => {
        const base: Record<string, string> = {...(fieldAlias ?? {})};
        if (fallbackField && Array.isArray(aliasToFallback) && aliasToFallback.length) {
            for (const name of aliasToFallback) {
                if (!name) continue;
                if (!(name in base)) base[name] = String(fallbackField);
            }
        }
        return Object.keys(base).length ? base : undefined;
    })();

    const rootOnFieldErrors = options?.rootOnFieldErrors ?? true;
    const rootServerValidationMessage = options?.rootServerValidationMessage ?? "Please fix the highlighted fields.";
    const rootClientValidationMessage = options?.rootClientValidationMessage ?? "Please fix the highlighted fields.";
    const clearRootOnAnyChange = options?.clearRootOnAnyChange ?? true;

    // install auto-clear subscription once per form
    ensureAutoClearSubscription(form, clearRootOnAnyChange);

    const resetForm = (values?: Partial<TIn>) => {
        // RHF: reset() preserves defaults if values omitted
        reset(values as any, {keepDefaultValues: !values});
    };

    return handleSubmit(
        async (data) => {
            try {
                const res = (await submitFn(data as unknown as TOut)) as Response | void;
                if (!res) return; // caller handled it

                if (successStatuses.includes(res.status)) {
                    clearErrors("root" as Path<TIn>);
                    const result = await parseSuccess(res);
                    await options?.onSuccess?.(result as TSuccess, {form, response: res, resetForm});
                    return;
                }

                let body: any = null;
                try {
                    body = await res.clone().json();
                } catch {
                }

                // Set field-level errors
                if (body && applyFieldErrors<TIn>(body, setError, fallbackField, {mapMessage, fieldAlias: computedFieldAlias})) {
                    console.error("RHF field-level errors:", body);
                    if (rootOnFieldErrors) {
                        setError("root" as Path<TIn>, {type: "server", message: rootServerValidationMessage});
                    }
                    focusFirstError(form);
                    return;
                }

                // Fallback root error
                const msg = (body && (body.detail || body.message)) || `${genericMessage} (HTTP ${res.status})`;
                setError("root" as Path<TIn>, {type: "server", message: String(msg)});
            } catch (err: any) {
                const response: Response | undefined = err?.response; // axios-like

                if (response) {
                    try {
                        const body = await response.clone().json();
                        if (body && applyFieldErrors<TIn>(body, setError, fallbackField, {mapMessage, fieldAlias: computedFieldAlias})) {
                            console.error("RHF field-level errors:", body);

                            if (rootOnFieldErrors) {
                                setError("root" as Path<TIn>, {
                                    type: "server",
                                    message: rootServerValidationMessage
                                });
                            }
                            focusFirstError(form);

                            return;
                        }
                    } catch { /* ignore */
                    }

                    setError("root" as Path<TIn>, {
                        type: "server",
                        message: `${genericMessage} (HTTP ${response.status})`
                    });
                    return;
                }

                setError("root" as Path<TIn>, {type: "server", message: "Network error, please try again."});
            }
        },
        (errs) => {
            console.error("RHF invalid submit. Errors:", errs);

            // client-side (Zod) invalid
            focusFirstError(form);
            if (rootOnFieldErrors) {
                form.setError("root" as Path<TIn>, {type: "validation", message: rootClientValidationMessage});
            }
        }
    );
}
