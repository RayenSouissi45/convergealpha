interface ImportMetaEnv {
  /** Repository URL, set by the deploy workflow; used for "view the methodology" links. */
  readonly VITE_REPO_URL?: string
  /** The every-minute live strategy values (the code repo's `live` branch), set by the deploy workflow. */
  readonly VITE_LIVE_URL?: string
}
