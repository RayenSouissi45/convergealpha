// German tax on investment income (Abgeltungsteuer), version 2026. Every number is dated and
// sourced; special cases (a personal income-tax rate below 25%, non-resident status, …) need the
// tax office or an adviser. Your bank's yearly tax statement is the official number.

export const TAX_RULES = {
  version: '2026',
  checked: '2026-10-14',
  /** Flat tax on capital income; the solidarity surcharge is 5.5% of that tax. */
  rate: 0.25,
  soli: 0.055,
  /** Saver's allowance per year (Sparer-Pauschbetrag), since 2023. */
  allowance: { single: 1000, joint: 2000 },
  /** Equity funds and ETFs (at least 51% stocks): 30% of gains and payouts are tax free. */
  equityFundExemption: 0.3,
  /** Basiszins for the yearly advance tax on funds (Vorabpauschale), set by the Ministry of Finance. */
  basiszins: { 2024: 0.0229, 2025: 0.0253, 2026: 0.032 } as Record<number, number>,
  /** US withholding on dividends with the treaty form (W-8BEN); counted toward the German tax. */
  usWithholding: 0.15,
  sources: [
    { name: 'Abgeltungsteuer and allowance 2026', url: 'https://www.steuerschroeder.de/Steuerrechner/Abgeltungsteuer.html' },
    { name: 'Church tax formula e / (4 + k), § 32d EStG', url: 'https://www.haufe.de/id/beitrag/abgeltungsteuer-1-systematik-HI6445752.html' },
    { name: 'Basiszins 2026: 3.20% (BMF, 13 Jan 2026)', url: 'https://www.otto-schmidt.de/news/steuerrecht/basiszins-zur-berechnung-der-vorabpauschale-gem-18-absatz-4-invstg-basiszins-zum-2-1-2026-2026-01-15.html' },
  ],
} as const

export type Filing = 'single' | 'joint'
/** Church tax rate: 0 (none), 8% (Bavaria, Baden-Württemberg) or 9% (other states). */
export type ChurchRate = 0 | 0.08 | 0.09

export interface TaxProfile {
  filing: Filing
  church: ChurchRate
  /** Allowance still unused this year, in euros (the bank uses it first). */
  allowanceLeft: number
}

export const DEFAULT_TAX: TaxProfile = { filing: 'single', church: 0, allowanceLeft: TAX_RULES.allowance.single }

export interface TaxBreakdown {
  /** Kapitalertragsteuer (25%, lower with church tax). */
  kapest: number
  soli: number
  church: number
  total: number
}

/** Tax on `e` euros of taxable capital income with `q` euros of foreign tax already paid
 * (credited) and church-tax rate k: Kapitalertragsteuer = (e − 4q) / (4 + k). */
export function capitalTax(e: number, k: ChurchRate = 0, q = 0): TaxBreakdown {
  const kapest = Math.max(0, (Math.max(0, e) - 4 * Math.max(0, q)) / (4 + k))
  const soli = kapest * TAX_RULES.soli
  const church = kapest * k
  return { kapest, soli, church, total: kapest + soli + church }
}

/** All-in rate on one euro of taxable income: 26.375% without church tax. */
export const effectiveRate = (k: ChurchRate = 0) => capitalTax(1, k).total

export type Kind = 'stock' | 'equityFund'

export interface GainTax {
  /** Part of the gain that counts (70% for equity funds). */
  taxable: number
  allowanceUsed: number
  tax: number
  /** The gain after tax. A loss is not taxed (it goes to the loss pot). */
  net: number
}

/** Tax on selling at a gain of `gain` euros. */
export function taxOnGain(gain: number, p: TaxProfile, kind: Kind = 'stock'): GainTax {
  if (!(gain > 0)) return { taxable: 0, allowanceUsed: 0, tax: 0, net: gain }
  const counted = kind === 'equityFund' ? gain * (1 - TAX_RULES.equityFundExemption) : gain
  const allowanceUsed = Math.min(counted, Math.max(0, p.allowanceLeft))
  const taxable = counted - allowanceUsed
  const tax = capitalTax(taxable, p.church).total
  return { taxable, allowanceUsed, tax, net: gain - tax }
}

/** German tax still due on a US dividend of `gross` euros after the 15% US withholding. */
export function usDividendTax(gross: number, p: TaxProfile): { withheld: number; german: number; net: number } {
  const withheld = gross * TAX_RULES.usWithholding
  const allowanceUsed = Math.min(gross, Math.max(0, p.allowanceLeft))
  const taxable = gross - allowanceUsed
  // The allowance covers the dividend first; the US tax is credited only on the taxed part.
  const credit = taxable > 0 ? withheld * (taxable / gross) : 0
  const german = capitalTax(taxable, p.church, credit).total
  return { withheld, german, net: gross - withheld - german }
}

/** Yearly advance tax base on an accumulating fund (Vorabpauschale), before the 30% exemption:
 * start value × Basiszins × 0.7, at most the year's real gain, less 1/12 per full month before
 * the purchase month. */
export function vorabpauschale(startValue: number, endValue: number, year: number, monthsHeld = 12): number {
  const bz = TAX_RULES.basiszins[year]
  if (bz === undefined || !(startValue > 0)) return 0
  const base = startValue * bz * 0.7 * (Math.min(12, Math.max(0, monthsHeld)) / 12)
  return Math.max(0, Math.min(base, endValue - startValue))
}
