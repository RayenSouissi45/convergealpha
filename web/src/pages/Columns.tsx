import { useEffect } from 'react'
import { Link, useLocation } from 'react-router'
import { Badge, Card, PageHeader } from '../components/ui'
import { COLUMN_DOCS, EXTRA_DOCS, statusText, type ColumnDoc } from '../lib/columnDocs'
import { COLUMNS, GROUP_ORDER } from '../lib/columns'
import { useHealth } from '../lib/health'

const PARTS: [keyof Omit<ColumnDoc, 'name' | 'status'>, string][] = [
  ['what', 'What it means'],
  ['how', 'How it is calculated'],
  ['example', 'Example'],
  ['read', 'Good or bad?'],
  ['source', 'Data source and updates'],
]

const slug = (g: string) => g.toLowerCase().replace(/[^a-z]+/g, '-')

const EXTRA_GROUPS = [...new Set(EXTRA_DOCS.map((d) => d.group))]

function Column({ id, where, doc, validated }: { id: string; where: string; doc: ColumnDoc; validated: string[] }) {
  const st = statusText(doc, validated)
  return (
    <section id={`col-${id}`} className="scroll-mt-28 py-3">
      <h3 className="text-base font-semibold">{doc.name}</h3>
      <p className="text-xs text-slate-500 dark:text-zinc-400">{where}</p>
      <dl className="mt-2 space-y-2 text-sm leading-relaxed">
        {PARTS.map(([k, title]) => (
          <div key={k}>
            <dt className="font-medium text-slate-700 dark:text-zinc-300">{title}</dt>
            <dd className="text-slate-600 dark:text-zinc-400">{doc[k]}</dd>
          </div>
        ))}
        <div>
          <dt className="font-medium text-slate-700 dark:text-zinc-300">Validated?</dt>
          <dd className="text-slate-600 dark:text-zinc-400">
            <span className="mr-1.5 inline-block align-middle">
              {st.validated === true ? <Badge tone="good">Validated</Badge> : st.validated === false ? <Badge tone="warn">Research mode</Badge> : <Badge tone="neutral">Measured data</Badge>}
            </span>
            {st.text}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-700 dark:text-zinc-300">Common mistakes</dt>
          <dd className="text-slate-600 dark:text-zinc-400">{doc.mistakes}</dd>
        </div>
      </dl>
    </section>
  )
}

export default function Columns() {
  const health = useHealth()
  const validated = health.state === 'ready' ? health.data.validated : []
  const { hash } = useLocation()

  // Deep links from the (i) tooltips: /columns#col-p_up_6m.
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash])

  return (
    <>
      <PageHeader title="Columns explained" subtitle="Every screener column and every Plan and Strategies number in plain English: what it means, how it is calculated and how to read it." />
      <nav aria-label="Column groups" className="-mx-4 mb-3 flex gap-1.5 overflow-x-auto px-4 pb-1">
        {[...GROUP_ORDER, ...EXTRA_GROUPS].map((g) => (
          <a key={g} href={`#/columns#group-${slug(g)}`} onClick={(e) => { e.preventDefault(); document.getElementById(`group-${slug(g)}`)?.scrollIntoView() }} className="inline-flex min-h-9 shrink-0 items-center rounded-full border border-slate-300 bg-white px-3 text-sm whitespace-nowrap dark:border-zinc-600 dark:bg-zinc-900">
            {g}
          </a>
        ))}
      </nav>
      <p className="mb-3 text-sm text-slate-600 dark:text-zinc-400">
        Values are shown as “—” when they are missing; tap the dash to see why. Probabilities say whether they passed the{' '}
        <Link to="/validation" className="underline">validation lab</Link>. Back to the <Link to="/screener" className="underline">Screener</Link>.
      </p>
      <div className="space-y-3">
        {GROUP_ORDER.map((g) => {
          const cols = COLUMNS.filter((c) => c.group === g)
          return (
            // Off-screen groups skip layout until they scroll into view (a long page on phones).
            <div key={g} id={`group-${slug(g)}`} className="scroll-mt-28 [contain-intrinsic-size:auto_1200px] [content-visibility:auto]">
              <Card title={g}>
                <div className="divide-y divide-slate-100 dark:divide-zinc-800">
                  {cols.map((c) => {
                    const doc = COLUMN_DOCS[c.key]
                    return doc ? <Column key={c.key} id={c.key} where={`Column header: “${c.label}”`} doc={doc} validated={validated} /> : null
                  })}
                </div>
              </Card>
            </div>
          )
        })}
        {EXTRA_GROUPS.map((g) => (
          <div key={g} id={`group-${slug(g)}`} className="scroll-mt-28 [contain-intrinsic-size:auto_1200px] [content-visibility:auto]">
            <Card title={`${g} page`}>
              <div className="divide-y divide-slate-100 dark:divide-zinc-800">
                {EXTRA_DOCS.filter((d) => d.group === g).map((d) => (
                  <Column key={d.id} id={d.id} where={`Shown on the ${g === 'Plan builder' ? 'Plan' : 'Strategies'} page`} doc={d.doc} validated={validated} />
                ))}
              </div>
            </Card>
          </div>
        ))}
      </div>
    </>
  )
}
