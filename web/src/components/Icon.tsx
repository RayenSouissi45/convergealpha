import type { IconName } from '../nav'

type Name = IconName | 'sun' | 'moon' | 'auto' | 'external' | 'chevron'

const PATHS: Record<Name, string> = {
  today: 'M3 11.5 12 4l9 7.5M5.5 9.5V20h13V9.5',
  picks: 'M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z',
  plan: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4',
  screener: 'M4 5h16M4 10h16M4 15h16M4 20h16M9 5v15',
  portfolio: 'M4 8h16v11H4zM9 8V5h6v3M4 13h16',
  health: 'M3 12h4l2.5-6 4 12 2.5-6H21',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  sun: 'M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66 1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14-1.41-1.41M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z',
  auto: 'M12 3a9 9 0 1 0 0 18V3z M12 3a9 9 0 0 1 0 18',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  chevron: 'M9 6l6 6-6 6',
}

export function Icon({ name, className = 'size-5' }: { name: Name; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === 'more' ? 3.5 : 1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
