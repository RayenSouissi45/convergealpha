import { Link } from 'react-router'
import { PageHeader } from '../components/ui'

export default function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" />
      <Link to="/" className="inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400">
        Back to Today
      </Link>
    </>
  )
}
