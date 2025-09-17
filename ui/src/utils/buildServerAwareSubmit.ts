import type {UseFormReturn, FieldValues, Path} from "react-hook-form";
import {applyFieldErrors} from "./serverErrors";

type SubmitFn<TValues> = (data: TValues) => Promise<Response | void>;

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

    /** If server error lacks a field path, map to this field; else to _root */
    fallbackField?: Path<TValues>;

    /** Message used for unmapped server errors */
    genericMessage?: string;

    /** Set a root-level summary when any field returns an error */
    rootOnFieldErrors?: boolean;                    // default: true

    /** Message to show at root for server-side validation errors */
    rootServerValidationMessage?: string;         // default: "Please fix the highlighted fields."

    /** Message to show at root for client-side invalid submits */
    rootClientValidationMessage?: string;         // default: "Please fix the highlighted fields."
};


export function buildServerAwareSubmit<TValues extends FieldValues, TSuccess = unknown>(
    form: UseFormReturn<TValues>,
    submitFn: SubmitFn<TValues>,
    options?: ServerAwareSubmitOptions<TValues, TSuccess>
) {
    const {handleSubmit, setError, reset} = form;

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
    const rootOnFieldErrors = options?.rootOnFieldErrors ?? true;
    const rootServerValidationMessage = options?.rootServerValidationMessage ?? "Please fix the highlighted fields.";
    const rootClientValidationMessage = options?.rootClientValidationMessage ?? "Please fix the highlighted fields.";

    const resetForm = (values?: Partial<TValues>) => {
        // RHF: reset() preserves defaults if values omitted
        reset(values as any, {keepDefaultValues: !values});
    };

    return handleSubmit(async (data) => {
        try {
            const res = (await submitFn(data)) as Response | void;
            if (!res) return; // caller handled it

            if (successStatuses.includes(res.status)) {
                const result = await parseSuccess(res);
                await options?.onSuccess?.(result as TSuccess, {form, response: res, resetForm});
                return;
            }

            // Try to map FastAPI-style errors
            let body: any = null;
            try {
                body = await res.clone().json();
            } catch { /* not JSON */
            }

            // Set field-level errors
            if (body && applyFieldErrors<TValues>(body, setError, fallbackField)) {
                console.error("RHF field-level errors:", body);
                if (rootOnFieldErrors) {
                    setError("root" as Path<TValues>, {type: "server", message: rootServerValidationMessage});
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
                    if (body && applyFieldErrors<TValues>(body, setError, fallbackField)) {
                        console.error("RHF field-level errors:", body);
                        if (rootOnFieldErrors) {
                            setError("root" as Path<TValues>, {type: "server", message: rootServerValidationMessage});
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
    }, (errs) => {
        console.error("RHF invalid submit. Errors:", errs);

        if (rootOnFieldErrors) {
            form.setError("root" as Path<TValues>, {
                type: "validation",
                message: rootClientValidationMessage
            });
        }
    });
}
