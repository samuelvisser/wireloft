import type {UseFormReturn, FieldValues, Path} from "react-hook-form";
import {applyFieldErrors} from "./serverErrors";
import type {ServerErrorItem} from "./serverMessageMap";

type SubmitFn<TValues> = (data: TValues) => Promise<Response | void>;

// internal constants/helpers
const SERVER_PREFIX = "server:" as const;
const INIT_FLAG: unique symbol = Symbol("serverErrorAutoClearInit");

// safe getter for nested paths (e.g., "items.0.name")
function get(obj: any, path: string) {
    return path.split(".").reduce((o, k) => (o ? o[k] : undefined), obj);
}

export type ServerAwareSubmitOptions<TValues extends FieldValues, TSuccess = unknown> = {
    onSuccess?: (result: TSuccess, ctx: {
        form: UseFormReturn<TValues>;
        response: Response;
        resetForm: (values?: Partial<TValues>) => void;
    }) => void | Promise<void>;

    /** HTTP statuses considered successful */
    successStatuses?: number[];

    /** Parse success payload. Return anything you want to receive in onSuccess. */
    parseSuccess?: (res: Response) => Promise<TSuccess>;

    /** If server error lacks a field path, map to this field; else to root */
    fallbackField?: Path<TValues>;

    /** Message used for unmapped server errors */
    genericMessage?: string;

    /** Override server error message for a specific field */
    mapMessage?: (err: ServerErrorItem, field: string) => string | undefined;

    /** Set a root-level summary when any field returns an error */
    rootOnFieldErrors?: boolean;                    // default: true

    /** Message to show at root for server-side validation errors */
    rootServerValidationMessage?: string;           // default: "Please fix the highlighted fields."

    /** Message to show at root for client-side invalid submits */
    rootClientValidationMessage?: string;           // default: "Please fix the highlighted fields."

    /** Clears the root banner when any field is changed */
    clearRootOnAnyChange?: boolean;                 // default true
};

function ensureAutoClearSubscription<TValues extends FieldValues>(
    form: UseFormReturn<TValues>,
    clearRootOnAnyChange: boolean
) {
    const f = form as any;
    if (f[INIT_FLAG]) return; // already installed

    const {watch, clearErrors, formState} = form;

    const sub = watch((_, info) => {
        const name = info?.name as Path<TValues> | undefined;
        if (!name) return;

        // If the edited field has a server-tagged error, clear it
        const err = get(formState.errors, String(name));
        if (err?.type && String(err.type).startsWith(SERVER_PREFIX)) {
            clearErrors(name);
        }

        // Optionally clear root banner as user starts editing
        if (clearRootOnAnyChange && (formState.errors as any)?.root) {
            clearErrors("root" as Path<TValues>);
        }
    });

    f[INIT_FLAG] = {unsubscribe: () => sub.unsubscribe()};
}

export function buildServerAwareSubmit<TValues extends FieldValues, TSuccess = unknown>(
    form: UseFormReturn<TValues>,
    submitFn: SubmitFn<TValues>,
    options?: ServerAwareSubmitOptions<TValues, TSuccess>
) {
    const {handleSubmit, setError, reset, clearErrors, setFocus} = form;

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
    const rootOnFieldErrors = options?.rootOnFieldErrors ?? true;
    const rootServerValidationMessage = options?.rootServerValidationMessage ?? "Please fix the highlighted fields.";
    const rootClientValidationMessage = options?.rootClientValidationMessage ?? "Please fix the highlighted fields.";
    const clearRootOnAnyChange = options?.clearRootOnAnyChange ?? true;

    // install auto-clear subscription once per form
    ensureAutoClearSubscription(form, clearRootOnAnyChange);

    const resetForm = (values?: Partial<TValues>) => {
        // RHF: reset() preserves defaults if values omitted
        reset(values as any, {keepDefaultValues: !values});
    };

    return handleSubmit(
        async (data) => {
            try {
                const res = (await submitFn(data)) as Response | void;
                if (!res) return; // caller handled it

                if (successStatuses.includes(res.status)) {
                    clearErrors("root" as Path<TValues>);
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
                if (body && applyFieldErrors<TValues>(body, setError, fallbackField, {mapMessage})) {
                    console.error("RHF field-level errors:", body);
                    if (rootOnFieldErrors) {
                        setError("root" as Path<TValues>, {type: "server", message: rootServerValidationMessage});
                    }
                    // Focus first field error (nice UX)
                    try {
                        const firstKey = Object.keys((form as any).formState.errors || {}).find(k => k !== "root");
                        if (firstKey) setFocus(firstKey as Path<TValues>);
                    } catch {
                    }
                    return;
                }

                // Fallback root error
                const msg = (body && (body.detail || body.message)) || `${genericMessage} (HTTP ${res.status})`;
                setError("root" as Path<TValues>, {type: "server", message: String(msg)});
            } catch (err: any) {
                const response: Response | undefined = err?.response; // axios-like

                if (response) {
                    try {
                        const body = await response.clone().json();
                        if (body && applyFieldErrors<TValues>(body, setError, fallbackField, {mapMessage})) {
                            console.error("RHF field-level errors:", body);

                            if (rootOnFieldErrors) {
                                setError("root" as Path<TValues>, {
                                    type: "server",
                                    message: rootServerValidationMessage
                                });
                            }
                            try {
                                const firstKey = Object.keys((form as any).formState.errors || {}).find(k => k !== "root");
                                if (firstKey) setFocus(firstKey as Path<TValues>);
                            } catch {
                            }
                            return;
                        }
                    } catch { /* ignore */
                    }

                    setError("root" as Path<TValues>, {
                        type: "server",
                        message: `${genericMessage} (HTTP ${response.status})`
                    });
                    return;
                }

                setError("root" as Path<TValues>, {type: "server", message: "Network error, please try again."});
            }
        },
        (errs) => {
            console.error("RHF invalid submit. Errors:", errs);

            // client-side (Zod) invalid
            try {
                const firstKey = Object.keys(errs)[0];
                if (firstKey) setFocus(firstKey as Path<TValues>);
            } catch {
            }
            if (rootOnFieldErrors) {
                form.setError("root" as Path<TValues>, {type: "validation", message: rootClientValidationMessage});
            }
        }
    );
}
