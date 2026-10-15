interface ImportMetaEnv {
  /** Repository URL, set by the deploy workflow; used for "view the methodology" links. */
  readonly VITE_REPO_URL?: string
  /** Raw files of the code repo, where live.yml pushes the live strategy values every minute (set by the deploy workflow). */
  readonly VITE_LIVE_RAW?: string
}
