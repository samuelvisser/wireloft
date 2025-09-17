import { useEffect } from "react";
import type { FieldValues, Path, UseFormReturn } from "react-hook-form";

// Simple getter for nested paths like "items.0.name"
function get(obj: any, path: string) {
  return path.split(".").reduce((o, k) => (o ? o[k] : undefined), obj);
}

export function useClearServerErrorsOnChange<T extends FieldValues>(
  form: UseFormReturn<T>,
  options?: { clearRootOnAnyChange?: boolean }
) {
  const { watch, clearErrors, formState } = form;
  const serverPrefix = "server:";
  const clearRootOnAnyChange = options?.clearRootOnAnyChange ?? true;

  useEffect(() => {
    const sub = watch((_, info) => {
      const name = info?.name as Path<T> | undefined;
      if (!name) return;

      // If this field currently has a server-tagged error, clear it.
      const err = get(formState.errors, String(name));
      if (err?.type && String(err.type).startsWith(serverPrefix)) {
        clearErrors(name);
      }
      // Clear root banner as soon as the user starts fixing things.
      if (clearRootOnAnyChange && (formState.errors as any)?.root) {
        clearErrors("root" as Path<T>);
      }
    });
    return () => sub.unsubscribe();
  }, [watch, clearErrors, formState.errors, serverPrefix, clearRootOnAnyChange]);
}
