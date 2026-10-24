import { useEffect, useId, useRef, useState } from 'react'
import './StudyControls.css'
export default function ChoiceSelect({ value, options, onChange, disabled, label }: {
  value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; disabled?: boolean; label: string
}) {
  const [open, setOpen] = useState(false), [index, setIndex] = useState(0)
  const id = useId(), root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null)
  const query = useRef(''), queryAt = useRef(0)
  const selected = options.findIndex(item => item.value === value)
  useEffect(() => { if (disabled) setOpen(false) }, [disabled])
  useEffect(() => { if (open) document.getElementById(`${id}-${index}`)?.scrollIntoView({ block: 'nearest' }) }, [id, index, open])
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  function choose(next: number) { if (options[next]) onChange(options[next].value); setOpen(false); trigger.current?.focus() }
  return <div ref={root} className="aura-choice" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false) }}>
    <button ref={trigger} type="button" role="combobox" aria-label={label} aria-expanded={open} aria-controls={id} aria-haspopup="listbox" aria-activedescendant={open ? `${id}-${index}` : undefined} disabled={disabled} onClick={() => { setIndex(Math.max(0, selected)); setOpen(current => !current) }} onKeyDown={event => {
      if (event.key === 'Tab') { setOpen(false); return }
      if (event.key === 'Escape') { if (open) { event.preventDefault(); event.stopPropagation(); setOpen(false) }; return }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
        event.preventDefault()
        if (!open) { setIndex(event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : Math.max(0, selected)); setOpen(true); return }
        if (event.key === 'Enter' || event.key === ' ') { choose(index); return }
        setIndex(current => event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length)
      } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        query.current = Date.now() - queryAt.current > 700 ? event.key : query.current + event.key; queryAt.current = Date.now()
        const found = options.findIndex(item => item.label.toLocaleLowerCase().startsWith(query.current.toLocaleLowerCase()))
        if (found >= 0) { setIndex(found); setOpen(true) }
      }
    }}><span>{options[selected]?.label ?? 'Choose an option'}</span><span aria-hidden="true">⌄</span></button>
    {open && <ul id={id} role="listbox" aria-label={label}>{options.map((item, n) => <li role="option" aria-selected={item.value === value} id={`${id}-${n}`} key={item.value} className={n === index ? 'is-highlighted' : ''} onPointerMove={() => setIndex(n)} onPointerDown={event => event.preventDefault()} onClick={() => choose(n)}>{item.label}<span aria-hidden="true">{item.value === value ? '✓' : ''}</span></li>)}</ul>}
  </div>
}
export function ItemCount({ value, onChange, disabled, label = 'Items' }: { value: number; onChange: (value: number) => void; disabled?: boolean; label?: string }) {
  return <fieldset className="aura-count" disabled={disabled}><legend>{label}</legend><div role="group" aria-label={label}>{[1, 2, 3, 4, 5].map(n => <button type="button" key={n} aria-label={`${n} ${label.toLowerCase()}`} aria-pressed={value === n} onClick={() => onChange(n)}>{n}</button>)}</div></fieldset>
}
