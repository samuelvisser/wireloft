import type {UseFormReturn, FieldValues, Path, FieldErrors} from "react-hook-form";
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
    successStatuses: number[];                      // default: [200, 201]

    /** Parse success payload. Return anything you want to receive in onSuccess. */
    parseSuccess: (res: Response) => Promise<TSuccess>;

    /** If an error lacks a field path, map to this field; else to root */
    fallbackField?: Path<TIn>;

    /** Message used for unmapped server errors */
    genericMessage: string;                         // default: "Something went wrong"

    /** Override server error message for a specific field */
    mapMessage?: (err: ServerErrorItem, field: string) => string | undefined;

    /** Move errors for these fields under another field (e.g. { slug: "name" }) */
    fieldAlias: Record<string, string>;

    /** List of server field names that should be routed to the fallbackField (if set) */
    aliasToFallback?: Path<TIn>[];

    /** Route all fields unknown to RHF to the fallbackField (fields are known if they are either registered or have a default value) */
    aliasToFallbackUnknown: boolean;                // default: true

    /** Set a root-level summary when any field returns an error */
    rootOnFieldErrors: boolean;                     // default: true

    /** Message to show at root for server-side validation errors */
    rootServerValidationMessage: string;            // default: "Please fix the highlighted fields."

    /** Message to show at root for client-side invalid submits */
    rootClientValidationMessage: string;            // default: "Please fix the highlighted fields."

    /** Clears the root banner when any field is changed */
    clearRootOnAnyChange: boolean;                  // default true
};

function getOptions<TIn extends FieldValues, TSuccess = unknown>(optionsProp?: Partial<ServerAwareSubmitOptions<TIn, TSuccess>>): ServerAwareSubmitOptions<TIn, TSuccess> {

    const defaults: ServerAwareSubmitOptions<TIn, TSuccess> = {
        successStatuses: [200, 201],
        parseSuccess: async (res: Response) => {
            if (res.status === 204) return undefined as unknown as TSuccess;
            const text = await res.text();
            if (!text) return undefined as unknown as TSuccess;
            try {
                return JSON.parse(text) as TSuccess;
            } catch {
                return undefined as unknown as TSuccess;
            }
        },
        genericMessage: "Something went wrong",
        fieldAlias: {},
        aliasToFallbackUnknown: true,
        rootOnFieldErrors: true,
        rootServerValidationMessage: "Please fix the highlighted fields.",
        rootClientValidationMessage: "Please fix the highlighted fields.",
        clearRootOnAnyChange: true,
    }
    if (!optionsProp) return defaults;
    return {...defaults, ...optionsProp};
}

/**
 * Adds aliasToFallback fields to the fieldAliases object
 *
 * @param options options the user passed to buildServerAwareSubmit
 */
function computedFieldAlias<TIn extends FieldValues, TSuccess = unknown>(options: ServerAwareSubmitOptions<TIn, TSuccess>): Record<string, string> {
    const {fallbackField: fallbackOpt, fieldAlias: fieldAliases, aliasToFallback} = options
    const fallbackTo: Path<TIn> = fallbackOpt ?? ("root" as Path<TIn>);

    // aliasToFallback takes precedence over aliasToFallbackUnknown
    if (Array.isArray(aliasToFallback) && aliasToFallback.length) {
        for (const fieldName of aliasToFallback) {
            if (!fieldName) continue;
            if (!(String(fieldName) in fieldAliases)) fieldAliases[String(fieldName)] = String(fallbackTo);
        }
    }
    return fieldAliases;
}

/**
 * Ensures that a subscription is created to automatically clear specific validation errors
 * (such as server-side errors) when changes are detected in the form or fields.
 *
 * @param {UseFormReturn} form - The form instance to which the subscription is applied.
 * It provides methods and state management utilities related to the form.
 * @param {boolean} clearRootOnAnyChange - Determines whether to clear the root-level errors
 * whenever any field changes.
 *
 * @return {void}
 */
function ensureAutoClearSubscription<TIn extends FieldValues>(form: UseFormReturn<TIn>, clearRootOnAnyChange: boolean): void {
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

/**
 * Make sure form knows about server errors
 *
 * This function uses server-side field names to map errors to the correct form fields
 * It also makes sure any unmapped errors get routed to the fallback (fallbackField or root form message)
 *
 * @param form the form the errors have to be applied to
 * @param response response data from the user's onSubmit implementation
 * @param options options the user passed to buildServerAwareSubmit
 *
 * @return void
 */
async function handleServerError<TIn extends FieldValues, TSuccess = unknown>(form: UseFormReturn<TIn>, response: Response, options: ServerAwareSubmitOptions<TIn, TSuccess>): Promise<void> {

    const {setError} = form;
    const {
        fallbackField,
        fieldAlias,
        aliasToFallbackUnknown,
        mapMessage,
        rootOnFieldErrors,
        rootServerValidationMessage,
        genericMessage
    } = options;

    let body: any = null;
    try {
        body = await response.clone().json();
    } catch {
    }

    if (body) {
        if (applyFieldErrors<TIn>(body, form, fallbackField, {
            mapMessage,
            fieldAlias,
            unknownToFallback: aliasToFallbackUnknown
        })) {
            console.error("RHF field-level errors:", body);
            if (rootOnFieldErrors) {
                setRootErrorIfEmpty(form, {type: "server", message: rootServerValidationMessage})
            }
            focusFirstError(form);
            return;
        }
    }

    const msg = (body && (body.detail || body.message)) || `${genericMessage} (HTTP ${response.status})`;
    setError("root" as Path<TIn>, {type: "server", message: String(msg)});
}

/**
 * Applies field aliases for errors in the local Zod schema
 *
 * If any validation error occurred locally in the Zod schema, we also need to handle aliased
 * fields showing their error in the right place. This is where we map that
 *
 * @param form the form the errors are applied to
 * @param errors the `FieldErrors` object representing current validation errors.
 * @param options options the user passed to buildServerAwareSubmit
 *
 * @return void
 */
export function applyLocalAliases<TIn extends FieldValues, TSuccess = unknown>(form: UseFormReturn<TIn>, errors: FieldErrors<TIn>, options: ServerAwareSubmitOptions<TIn, TSuccess>) {
    const {fieldAlias: aliasMap, fallbackField: fallbackOpt, rootClientValidationMessage} = options;
    const {setError, watch} = form;
    const fallbackTo: Path<TIn> = fallbackOpt ?? ("root" as Path<TIn>);

    // Create aliases for unknown fields
    if (options.aliasToFallbackUnknown) {
        const knownFields: string[] = Object.keys(watch());
        for (const errorField of Object.keys(errors)) {
            if (!(errorField in knownFields) && !(errorField in aliasMap)) {
                aliasMap[errorField] = fallbackTo;
            }
        }
    }

    // Apply aliases
    for (const origField of Object.keys(aliasMap)) {
        const err = (errors)?.[origField];
        if (err) {
            const aliasFallback: Path<TIn> = aliasMap[origField] as Path<TIn>;
            const msg = String(err.message ?? rootClientValidationMessage);

            setError(aliasFallback, {
                type: String(err.type || 'validation'),
                message: `Error in field ${origField}: ${msg}`
            });
            form.clearErrors(origField as Path<TIn>);
        }
    }
}

/**
 * Small helper function to set an error on the form root field if it does not already contain an error
 *
 * @param form the form the root error should be applied to
 * @param error the error message to be applied
 *
 * @return void
 */
function setRootErrorIfEmpty<TIn extends FieldValues>(form: UseFormReturn<TIn>, error: {
    type: string,
    message: string
}): void {
    if (!form.getFieldState("root" as Path<TIn>)?.error?.message) {
        form.setError("root" as Path<TIn>, {type: error.type, message: error.message});
    }
}

/**
 * Builds a server-aware submit handler for forms using React Hook Form, integrating server-side validation
 * with client-side error handling and customizable behavior for form submission and response handling.
 *
 * @param {UseFormReturn} form - The React Hook Form instance that manages the form state and validation.
 * @param {SubmitFn} submitFn - The user-provided function invoked when the form is successfully submitted,
 *                                    expected to handle the form data and return a server response or void.
 * @param {Partial<ServerAwareSubmitOptions>} [optionsProp] - Optional configuration object that
 *                                                                           defines the behavior and overrides
 *                                                                           for success handling, error processing,
 *                                                                           and form interactions.
 *
 * @return {Function} A composed submit handler function that resolves the submission process,
 *                    handling both client-side validation failures and server-side responses.
 *                    This function is to be passed to the form onSubmit
 */
export function buildServerAwareSubmit<TIn extends FieldValues, TOut extends FieldValues = TIn, TSuccess = unknown>(
    form: UseFormReturn<TIn>,
    submitFn: SubmitFn<TOut>,
    optionsProp?: Partial<ServerAwareSubmitOptions<TIn, TSuccess>>
) {
    const {handleSubmit, reset, clearErrors} = form;

    const options = getOptions(optionsProp);
    const {
        successStatuses,
        parseSuccess,
        clearRootOnAnyChange,
        rootOnFieldErrors,
        rootClientValidationMessage
    } = options;
    options.fieldAlias = computedFieldAlias(options);

    // install auto-clear subscription once per form
    ensureAutoClearSubscription(form, clearRootOnAnyChange);

    const resetForm = (values?: Partial<TIn>) => {
        // RHF: reset() preserves defaults if values omitted
        reset(values as any, {keepDefaultValues: !values});
    };

    return handleSubmit(
        async (dataIn: TIn) => {
            // Arrives here only if Zod validation passed
            const dataOut = dataIn as unknown as TOut;

            try {
                // Run user- provided submit handler
                const response = (await submitFn(dataOut)) as Response | void;
                if (!response) return; // caller handled it

                if (successStatuses.includes(response.status)) {
                    clearErrors("root" as Path<TIn>);
                    const result = await parseSuccess(response);
                    await options?.onSuccess?.(result as TSuccess, {form, response: response, resetForm});
                    return;
                }

                await handleServerError(form, response, options);
                return;
            } catch (err: any) {
                const response: Response | undefined = err?.response; // axios-like

                if (response) {
                    await handleServerError(form, response, options);
                }

                setRootErrorIfEmpty(form, {type: "server", message: "Network error, please try again."})
            }
        },
        (errs: FieldErrors<TIn>) => {
            // Zod validation failed
            console.error("RHF invalid local submit. Errors:", errs);

            applyLocalAliases(form, errs, options);
            focusFirstError(form);

            if (rootOnFieldErrors) {
                setRootErrorIfEmpty(form, {type: "validation", message: rootClientValidationMessage})
            }
        }
    );
}