import { useRef, useState } from 'react'
import MemoryDialog from './MemoryDialog'
import { cleanDisplayName } from './studyPlanModel'
import './AccountMenu.css'

type Props = { name: string; courseId: string; onSignOut?: () => void; signingOut?: boolean; disabled?: boolean; demo?: boolean }
export default function AccountMenu({ name, courseId, onSignOut, signingOut, disabled, demo = false }: Props) {
  const [memoryOpen, setMemoryOpen] = useState(false)
  const menu = useRef<HTMLDetailsElement>(null)
  return <div className="aura-account">
    <details ref={menu} onKeyDown={e => { if (e.key === 'Escape') { menu.current!.open = false; menu.current?.querySelector('summary')?.focus() } }}>
      <summary><span className="aura-account__avatar" aria-hidden="true">{cleanDisplayName(name).slice(0, 1).toUpperCase()}</span><span><strong>{cleanDisplayName(name)}</strong><small>{demo ? 'Demo account' : 'Your account'}</small></span><span aria-hidden="true">⌄</span></summary>
      <div className="aura-account__items"><button type="button" disabled={!courseId} onClick={() => { setMemoryOpen(true); menu.current!.open = false }}>What Aura remembers</button>{onSignOut && <button type="button" disabled={disabled || signingOut} onClick={onSignOut}>{signingOut ? 'Signing out…' : 'Sign out'}</button>}</div>
    </details>
    {memoryOpen && <MemoryDialog courseId={courseId} onClose={() => { setMemoryOpen(false); menu.current?.querySelector('summary')?.focus() }} />}
  </div>
}
