import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

interface TipProps {
  /** What the tooltip explains. Shown on hover, keyboard focus, or tap. */
  content: ReactNode
  /** The visible trigger text. */
  children: ReactNode
  /** Accessible name when the trigger text alone is unclear (e.g. "—"). */
  label?: string
  className?: string
}

const MARGIN = 8

/** Tooltip that also works on phones: tap to open, tap elsewhere or scroll to close. */
export function Tip({ content, children, label, className = '' }: TipProps) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const id = useId()
  const wrapRef = useRef<HTMLSpanElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const tipRef = useRef<HTMLSpanElement>(null)
  const lastPointer = useRef('')

  // Every open/close goes through here so a stale position is never reused.
  const show = useCallback((next: boolean) => {
    setOpen(next)
    if (!next) setPos(null)
  }, [])

  useLayoutEffect(() => {
    if (!open) return
    const trigger = triggerRef.current?.getBoundingClientRect()
    const tip = tipRef.current?.getBoundingClientRect()
    if (!trigger || !tip) return
    const left = Math.max(
      MARGIN,
      Math.min(trigger.left + trigger.width / 2 - tip.width / 2, window.innerWidth - tip.width - MARGIN),
    )
    const above = trigger.top - tip.height - 6
    setPos({ top: above >= MARGIN ? above : trigger.bottom + 6, left })
  }, [open])

  useEffect(() => {
    if (!open) return
    const close = () => show(false)
    const onPointerDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) close()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    window.addEventListener('scroll', close, { passive: true, capture: true })
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', close, { capture: true })
      window.removeEventListener('resize', close)
    }
  }, [open, show])

  return (
    <span
      ref={wrapRef}
      className="inline-flex"
      onPointerEnter={(e) => e.pointerType === 'mouse' && show(true)}
      onPointerLeave={(e) => e.pointerType === 'mouse' && show(false)}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onPointerDown={(e) => (lastPointer.current = e.pointerType)}
        // Mouse users already opened it by hovering; touch and keyboard (Enter/Space) toggle.
        onClick={() => {
          const pointer = lastPointer.current
          lastPointer.current = ''
          show(pointer === 'mouse' ? true : !open)
        }}
        onBlur={() => show(false)}
        className={`cursor-help underline decoration-dotted decoration-slate-400 underline-offset-4 dark:decoration-zinc-500 ${className}`}
      >
        {children}
      </button>
      {open && (
        <span
          ref={tipRef}
          role="tooltip"
          id={id}
          style={pos ? { top: pos.top, left: pos.left } : { top: 0, left: 0, visibility: 'hidden' }}
          className="fixed z-50 w-max max-w-[min(18rem,calc(100vw-1rem))] rounded-lg bg-slate-900 px-3 py-2 text-left text-xs leading-relaxed font-normal text-white shadow-lg dark:bg-zinc-700"
        >
          {content}
        </span>
      )}
    </span>
  )
}
