import { useEffect, useRef } from 'react'
/** CSS handles the animations; observers stop them when not visible. */
export function usePageMotion() {
  const root=useRef<HTMLDivElement>(null)
  useEffect(()=>{const node=root.current;if(!node)return;node.classList.add('motion-ready');const reduced=matchMedia('(prefers-reduced-motion: reduce)');let frame=0
    const observer=new IntersectionObserver(entries=>{entries.forEach(e=>{e.target.classList.toggle('is-visible',e.isIntersecting);if(e.isIntersecting)e.target.classList.add('has-entered')})},{threshold:.12})
    const observed=new WeakSet<Element>();const register=()=>node.querySelectorAll('[data-reveal],[data-loop]').forEach(el=>{if(!observed.has(el)){observed.add(el);observer.observe(el)}});register();const additions=new MutationObserver(register);additions.observe(node,{childList:true,subtree:true})
    const visibility=()=>node.classList.toggle('is-hidden',document.hidden)
    const scroll=()=>node.classList.toggle('is-scrolled',window.scrollY>30)
    const move=(e:PointerEvent)=>{if(reduced.matches||e.pointerType!=='mouse')return;cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{const magnetic=(e.target as Element).closest<HTMLElement>('[data-magnetic]');if(magnetic){const b=magnetic.getBoundingClientRect();magnetic.style.setProperty('--mx',`${Math.max(-6,Math.min(6,(e.clientX-b.left-b.width/2)*.06))}px`);magnetic.style.setProperty('--my',`${Math.max(-6,Math.min(6,(e.clientY-b.top-b.height/2)*.06))}px`)}const target=(e.target as Element).closest<HTMLElement>('[data-spotlight]');if(!target)return;const r=target.getBoundingClientRect();target.style.setProperty('--pointer-x',`${e.clientX-r.left}px`);target.style.setProperty('--pointer-y',`${e.clientY-r.top}px`);const glow=target.querySelector<HTMLElement>('.landing-glow');if(glow){glow.style.setProperty('--gx',`${(e.clientX-r.left-r.width/2)*.035}px`);glow.style.setProperty('--gy',`${(e.clientY-r.top-r.height/2)*.035}px`)}})}
    visibility();scroll();document.addEventListener('visibilitychange',visibility);window.addEventListener('scroll',scroll,{passive:true});node.addEventListener('pointermove',move)
    return()=>{observer.disconnect();additions.disconnect();cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('scroll',scroll);node.removeEventListener('pointermove',move)}
  },[])
  return root
}
