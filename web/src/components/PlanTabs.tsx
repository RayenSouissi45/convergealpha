import { NavLink } from 'react-router'

const tab = ({ isActive }: { isActive: boolean }) =>
  `inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold ${isActive ? 'bg-white text-slate-900 shadow-xs dark:bg-zinc-950 dark:text-zinc-100' : 'text-slate-600 dark:text-zinc-400'}`

/** Plan has two parts: investing an amount now, and a savings plan towards a goal. */
export function PlanTabs() {
  return (
    <nav aria-label="Plan" className="mb-3 inline-flex max-w-full rounded-xl bg-slate-100 p-1 dark:bg-zinc-800">
      <NavLink to="/plan" end className={tab}>
        Invest an amount now
      </NavLink>
      <NavLink to="/plan/goal" className={tab}>
        Savings plan &amp; goal
      </NavLink>
    </nav>
  )
}
