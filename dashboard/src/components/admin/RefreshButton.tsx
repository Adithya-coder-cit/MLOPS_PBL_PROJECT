import './RefreshButton.css'

interface RefreshButtonProps {
  onRefresh: () => void
  loading: boolean
}

export function RefreshButton({ onRefresh, loading }: RefreshButtonProps) {
  return (
    <button type="button" className="rw-refresh-button" onClick={onRefresh} disabled={loading}>
      {loading ? 'Refreshing…' : 'Refresh'}
    </button>
  )
}
