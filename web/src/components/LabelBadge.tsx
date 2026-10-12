import { LABEL_TONE } from '../lib/labels'
import { Badge } from './ui'

export function LabelBadge({ label }: { label: string }) {
  return <Badge tone={LABEL_TONE[label] ?? 'neutral'}>{label}</Badge>
}
