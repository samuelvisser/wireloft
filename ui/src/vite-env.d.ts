/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WIRELOFT_VERSION: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
