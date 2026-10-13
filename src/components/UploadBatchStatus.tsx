import type { UploadEntry } from '../services/preparationApi'

export default function UploadBatchStatus({ entries, busy, onRetry }: { entries: UploadEntry[]; busy: boolean; onRetry: () => void }) {
  if (!entries.length) return null
  const queued = entries.filter(entry => entry.state === 'queued').length
  const failed = entries.filter(entry => entry.state === 'failed')
  return <section className="aura-preparation" aria-label="File uploads">
    <p role="status">{queued} of {entries.length} files uploaded to the preparation queue.{busy ? ' Uploading the remaining files…' : queued ? ' Preparation continues in the background.' : ''}</p>
    {entries.filter(entry => entry.state === 'waiting' || entry.state === 'uploading').map((entry, index) => <p key={index}>{entry.file.name}: {entry.state === 'uploading' ? 'Uploading…' : 'Waiting to upload'}</p>)}
    {failed.map((entry, index) => <p key={index} className="aura-preparation-error" role="alert">{entry.file.name}: {entry.error}</p>)}
    {failed.length > 0 && <button type="button" disabled={busy} onClick={onRetry}>Retry failed uploads only</button>}
  </section>
}
