import type { Tone } from '../components/ui'

export const LABEL_TONE: Record<string, Tone> = {
  'STRONG BUY — TOP CONVICTION': 'good',
  BUY: 'good',
  WATCH: 'warn',
  HOLD: 'neutral',
  ROTATE: 'warn',
  'SELL / RISK WARNING': 'bad',
  'NO TRADE': 'neutral',
}
