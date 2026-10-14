// Safe-deploy gate: refuses to publish site data that is clearly broken. When it fails, the deploy
// stops and the live site keeps the previous version (an automatic rollback).
//
// Usage: node scripts/gate.mjs <data-dir> [live-site-url]
// Fails when:
//  - a JSON file does not parse, or health.json / screener.json is missing while the live site has them;
//  - the screener has less than half the live site's stocks;
//  - the data is older than what is live (it would roll the site back in time).
// The live site being unreachable (first deploy, network) is not a failure.
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const dir = process.argv[2] ?? 'public/data'
const live = (process.argv[3] ?? process.env.SITE_URL ?? 'https://rayensouissi45.github.io/convergealpha').replace(/\/$/, '')
const problems = []

function readLocal(name) {
  const p = join(dir, name)
  if (!existsSync(p)) return undefined
  try {
    return JSON.parse(readFileSync(p, 'utf8'))
  } catch (e) {
    problems.push(`${name} does not parse: ${e.message}`)
    return null
  }
}

async function readLive(name) {
  try {
    const r = await fetch(`${live}/data/${name}`, { signal: AbortSignal.timeout(15000) })
    if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) return undefined
    return await r.json()
  } catch {
    return undefined
  }
}

const files = existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith('.json')) : []
for (const f of files) readLocal(f)

const [liveHealth, liveScreener] = await Promise.all([readLive('health.json'), readLive('screener.json')])
const health = readLocal('health.json')
const screener = readLocal('screener.json')

if (liveHealth && health === undefined) problems.push('health.json is missing but the live site has one')
if (liveScreener && screener === undefined) problems.push('screener.json is missing but the live site has one')
const n = screener?.rows?.length ?? screener?.count
const liveN = liveScreener?.rows?.length ?? liveScreener?.count
if (typeof n === 'number' && typeof liveN === 'number' && liveN > 100 && n < liveN / 2) {
  problems.push(`screener has ${n} stocks, the live site ${liveN}`)
}
if (health?.generated_at && liveHealth?.generated_at && health.generated_at < liveHealth.generated_at) {
  problems.push(`data from ${health.generated_at} is older than the live site's (${liveHealth.generated_at})`)
}

const summary = `${files.length} files; screener ${n ?? '—'} stocks (live ${liveN ?? 'unknown'}); data ${health?.generated_at ?? '—'} (live ${liveHealth?.generated_at ?? 'unknown'})`
if (problems.length) {
  console.error(`::error::Deploy gate failed, the live site keeps its previous version. ${problems.join('; ')}`)
  console.error(summary)
  process.exit(1)
}
console.log(`Deploy gate passed: ${summary}`)
