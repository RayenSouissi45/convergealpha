import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Renders children only once the placeholder scrolls near the viewport, so heavy chart
 * libraries are not downloaded and parsed before they are needed. */
export function WhenVisible({ children, height }: { children: ReactNode; height: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    if (visible || !ref.current) return
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true)
          obs.disconnect()
        }
      },
      { rootMargin: '200px' },
    )
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [visible])
  return visible ? <>{children}</> : <div ref={ref} className={height} aria-hidden="true" />
}
