/** Only publish measured facts. null values are deliberately hidden. */
export const siteFacts = {
  name: 'Aura',
  repoUrl: 'https://github.com/Bhavishya007-bit/Aura-NVIDIA',
  demoVideoUrl: '', // [FILL IN] Public YouTube URL, after publishing the demo.
  canonicalUrl: '', // [FILL IN] Public deployment origin, if deployed.
  contactUrl: '', // [FILL IN] Contact mailto: or HTTPS link.
  privacyUrl: '', // [FILL IN] Reviewed privacy policy URL.
  termsUrl: '', // [FILL IN] Reviewed terms URL.
  judgeInstructions: '[FILL IN] Add the public test-build download and private credential instructions before submission. Never put passwords or API keys here.',
  metrics: [
    {label: 'Citation accuracy', value: null as number|null, unit: '%', context: ''},
    {label: 'Cached-token rate', value: null as number|null, unit: '%', context: ''},
    {label: 'Cost per answer', value: null as number|null, unit: ' USD', context: ''},
  ],
}
export function youtubeEmbed(url:string) {try{const u=new URL(url);const id=u.hostname==='youtu.be'?u.pathname.slice(1):['youtube.com','www.youtube.com'].includes(u.hostname)?u.searchParams.get('v'):null;return id&&/^[\w-]{11}$/.test(id)?`https://www.youtube-nocookie.com/embed/${id}`:null}catch{return null}}
