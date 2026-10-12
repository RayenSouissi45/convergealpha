import { Tip } from './Tip'

/** The only way the site shows an absent value: "—" plus the reason. Never a made-up number. */
export function Missing({ reason }: { reason: string }) {
  return (
    <Tip content={reason} label={`Not available: ${reason}`} className="text-slate-500 dark:text-zinc-400">
      —
    </Tip>
  )
}
