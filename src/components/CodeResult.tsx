import { useState } from 'react'
import type { AgentRun, CodeOutput } from '../services/agentApi'
import { downloadCodeArtifact } from '../services/agentApi'

export function savedCodeOutput(run: AgentRun): CodeOutput | undefined {
  const value = run.result?.code_result ?? [...run.steps].reverse().find(step => step.tool === 'code_execute' && step.state === 'completed')?.observation
  if (!value || typeof value !== 'object') return undefined
  const output = value as CodeOutput
  return ['succeeded', 'failed', 'timed_out'].includes(output.status) && typeof output.stdout === 'string' && typeof output.stderr === 'string' && Array.isArray(output.artifacts) ? output : undefined
}

export default function CodeResult({ run, courseId }: { run: AgentRun; courseId: string }) {
  const output = savedCodeOutput(run)
  const program = [...run.steps].reverse().find(step => step.tool === 'code_execute' && step.state === 'completed')?.action?.code
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  if (!output) return null
  async function download(name: string) {
    if (busy) return
    setBusy(name); setError('')
    try {
      const blob = await downloadCodeArtifact(courseId, run.id, name)
      const url = URL.createObjectURL(blob), link = document.createElement('a')
      link.href = url; link.download = name; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { setError('This file could not be downloaded. Please try again.') }
    finally { setBusy('') }
  }
  return <div className="plan-code-result">
    <p role="status">{output.status === 'succeeded' ? 'Python finished successfully.' : output.status === 'timed_out' ? 'The calculation reached its time limit.' : 'Python stopped with an error.'}</p>
    <p className="plan-caption">These are captured execution results. A successful run does not verify the explanation or the underlying data.</p>
    {run.result?.text && <div className="plan-code-explanation">{run.result.text}</div>}
    {program && <details><summary>View Python code</summary><pre tabIndex={0}>{program}</pre></details>}
    <section aria-label="Python output"><h3>Output</h3><pre tabIndex={0}>{output.stdout || 'No printed output.'}</pre>{output.stdout_truncated && <p className="plan-caption">Output was shortened to fit the capture limit.</p>}</section>
    {output.stderr && <details><summary>Python messages</summary><pre tabIndex={0}>{output.stderr}</pre>{output.stderr_truncated && <p>Messages were shortened.</p>}</details>}
    {output.artifacts.length > 0 && <section aria-label="Saved output files"><h3>Files from this run</h3><ul className="plan-code-files">{output.artifacts.map(item => <li key={item.name}><strong>{item.name}</strong><small>{item.size.toLocaleString()} bytes</small><button type="button" disabled={!!busy} onClick={() => void download(item.name)}>{busy === item.name ? 'Downloading…' : 'Download'}<span className="plan-sr-only"> {item.name}</span></button></li>)}</ul></section>}
    {output.missing_outputs?.length > 0 && <p className="plan-caption">Requested files not saved: {output.missing_outputs.join(', ')}.</p>}
    {error && <p role="alert">{error}</p>}
  </div>
}
