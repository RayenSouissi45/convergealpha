import { Link } from 'react-router'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/ui'
import { SECONDARY_NAV } from '../nav'

export default function More() {
  return (
    <>
      <PageHeader title="More" />
      <nav aria-label="More pages">
        <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
          {SECONDARY_NAV.map((item) => (
            <li key={item.to}>
              <Link to={item.to} className="flex min-h-14 items-center justify-between px-4 text-base hover:bg-slate-50 dark:hover:bg-zinc-800">
                {item.label}
                <Icon name="chevron" className="size-5 text-slate-400" />
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </>
  )
}
