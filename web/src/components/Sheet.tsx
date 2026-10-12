import { useEffect, useRef, type ReactNode } from 'react'

/** Modal panel (bottom sheet on phones, centered on desktop) built on <dialog>. */
export function Sheet({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) {
      if (typeof d.showModal === 'function') d.showModal()
      else d.setAttribute('open', '')
    }
    if (!open && d.open) {
      if (typeof d.close === 'function') d.close()
      else d.removeAttribute('open')
    }
  }, [open])

  return (
    // Backdrop clicks close the sheet; keyboard users close it with Escape (onCancel) or "Done".
    // oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={ref}
      aria-label={title}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose() // click on the backdrop
      }}
      className="m-0 mt-auto max-h-[85dvh] w-full max-w-none rounded-t-2xl border border-slate-200 bg-white p-0 text-slate-900 backdrop:bg-black/40 sm:m-auto sm:max-w-lg sm:rounded-2xl dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
    >
      <div className="flex max-h-[85dvh] flex-col">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2 dark:border-zinc-800">
          <h2 className="text-base font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="min-h-11 rounded-lg px-3 text-sm font-medium text-teal-700 dark:text-teal-400">
            Done
          </button>
        </div>
        <div className="overflow-y-auto px-4 py-3">{children}</div>
        {footer && <div className="border-t border-slate-200 px-4 py-2 dark:border-zinc-800">{footer}</div>}
      </div>
    </dialog>
  )
}
