// Use form type with root for general error messages
export type WithRoot<T> = T & {
  root?: { message?: string }
};