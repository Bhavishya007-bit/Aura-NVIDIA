# Aura: ink and ember

This frontend refresh preserves authentication, API paths, request payloads, source selection, generation/cancellation, saved workspace data and backend behavior. Signed-out `/` now shows the public product page; `/login` and `/signup` retain the existing forms. Signed-in `/` retains Chat or the saved workspace. `/welcome` is an explicit public-page link for signed-in users; `/judges` is public but grants no account access.

The supplied brief was available. Its two referenced screenshots were not attached to this request, so the design follows the written direction rather than a copied layout.

## Stage 1: shared design system

Files: `src/design-system.css`, `src/components/ui/index.tsx`, `src/main.tsx`, `package.json`, `package-lock.json`.

- Ink/cream/ember variables, spacing, radii, elevations, motion durations and both themes.
- The requested ember is retained as the brand color. Small text on pale ember uses a darker accessible `--ember-text` token; the literal brand pairing fails 4.5:1.
- Button variants/sizes/loading/pill; IconButton; Card; Chip and CitationChip; arrow-key Tabs; Segmented control; Switch; labelled Input/Textarea; existing keyboard-aware ChoiceSelect exported as Select; Tooltip; disclosure Popover; native modal/Drawer; Toast; Skeleton; EmptyState; progress bar/ring; Badge; Avatar; Kbd.
- Native modal dialogs provide focus containment, Escape and return focus. Dropdowns retain their existing keyboard/typeahead behavior.
- Existing app components map to common palette tokens. Compatibility layout CSS remains deliberately intact. This is not a wholesale rewrite or deletion of every legacy stylesheet.
- `lucide-react` is the only new production dependency, for consistent vector icons. Google Fonts supplies Manrope and Instrument Serif with `display=swap`; system/Georgia fallbacks keep the app usable offline. CSS and IntersectionObserver are sufficient for motion, so no motion runtime is added.

Hand check: tab focus, disabled buttons, menu arrows/typeahead, theme switching, native dialogs with your screen reader.

## Stage 2: public product pages

Files: `src/pages/LandingPage.tsx`, `src/pages/LandingExample.tsx`, `src/pages/LandingSections.tsx`, `src/pages/LandingPage.css`, `src/pages/JudgesPage.tsx`, `src/config/siteFacts.ts`, `src/App.tsx`.

- Floating navigation, Features disclosure, mobile drawer, theme control and preserved auth links.
- Always-dark hero, subtle ember glow, serif accent, two CTAs, live HTML product sample.
- Demo question animation, answer reveal, citation preview and click-to-open sample slide. The sample is explicitly illustrative, never a fabricated user upload or actual model response.
- Truth strip contains no invented statistics or partnership claims.
- Three-step explanation, six feature cards, hover/focus micro-motion, sample plan checkbox, flashcard reveal, memory delete/undo and coverage toggle.
- Architecture diagram, measured-fact slots, privacy/control cards, keyboard FAQ, final CTA and footer.
- YouTube is only embedded after the user explicitly opens the configured demo. Empty configuration shows `[FILL IN]`. No autoplay or cookie banner; no new analytics/non-essential cookie code.
- Public judges page contains a 60-second tour and repository/document links, with clearly marked instructions to fill in.
- Main public page, below-fold sections, auth, Chat and Study workspace use lazy modules. Existing global compatibility CSS is still shared.

Hand check: signed-out `/`, signed-in `/`, `/welcome`, `/judges`, mobile menu, sign-in/up, every CTA, samples, video once configured.

## Stage 3: app polish

Files: `src/components/ChatHome.tsx`, `src/components/TeachingText.tsx`, `src/components/StudyWorkspace.tsx`, `src/components/StudyOverview.tsx`, `src/components/ProgressV2.tsx`, `src/components/AgentPanel.tsx`, `src/components/MemoryDialog.tsx`, plus the shared stylesheet.

- Chat follows the real stored theme, with a theme control and About Aura link.
- Existing Stop/escape/partial results, material chips, edit-and-resend and follow-ups remain operational.
- Answer copy with status feedback; regenerate uses the existing send path and is disabled if the answer's original material scope differs from the current scope.
- Streamed content gets a subtle caret. Source/background headings have distinct styling, including Markdown heading variants.
- Citations preserve real material/page information and the existing original-file viewer; a hover title previews the provided excerpt without adding a network call. Rich slide-image hover is implemented only in the illustrative landing sample. App slides still load on explicit click through the existing viewer.
- Skeletons replace primary material, saved-work, progress, agent-plan and memory loading text. Existing tool-generation status remains explicit and cancellable rather than being hidden behind skeletons.
- Existing save/delete/undo state and messages are retained. No new backend or artificial progress/result values.
- Full per-component icon migration and deletion of all legacy CSS are not asserted; existing proven component structure remains compatible.

Hand check: real chat generation/Stop, copy, edit/resend, regenerate using original material, two-material question, every study tab, source viewer, memory CRUD/undo, saved study set, existing task completion/cancel.

## Stage 4: motion

Files: `src/hooks/usePageMotion.ts`, `src/pages/LandingPage.tsx`, `src/pages/LandingPage.css`, `src/design-system.css`.

- Duration/easing tokens, staggered reveal, hover lift, cursor spotlight, primary CTA magnetic offset capped at 6px, transform-only shimmer and button press.
- IntersectionObserver pauses feature/hero loops offscreen; document visibility pauses animations and the demo timer.
- Reduced-motion disables motion, drift, caret and demo cycling and shows final states.
- No scroll-jacking, audio, WebGL, video background or full-screen preloader.
- Metrics remain hidden until real numbers AND their measurement context are supplied. No animated fake counters.

Hand check: motion preference enabled/disabled, tab hiding/restoring, mobile scrolling, pointer movement, no jump when a sample cycles.

## Stage 5: verification and packaging

Files: `scripts/check_landing.mjs`, `scripts/check_responsive.mjs`, `scripts/smoke_browser.mjs`, `.github/workflows/production.yml`, `.github/workflows/judge-release.yml`, `index.html`, `public/favicon.svg`, `public/favicon-32.png`, `public/apple-touch-icon.png`, `public/social-card.svg`, `public/social-card.png`, `public/robots.txt`, `Dockerfile`, `scripts/package_judge.py`.

- Public browser checks at 360/390/768/1280/1920/2560 in both themes: no horizontal overflow, theme persistence, source/modal interactions, Escape/focus restoration, keyboard mobile menu, judges and login routes; no API calls from signed-out sample interactions.
- Existing signed-in fixture checks still cover all eight workspace tabs, 320–3840 widths, five material selection and visible/reachable composers. The login test explicitly opens `/login` now that `/` is public.
- Real anonymous-access smoke still requires 401 from `/api/auth/me`; the landing page does not relax server access controls.
- Metadata, favicons and a real 1200×630 PNG generated from the included SVG template. Public assets are copied into Docker and the downloadable source package.
- Automated page audits and screenshots were run locally. See the final verification notes below for measured results and limitations. A local audit is not a hosted production SLA.

## Editable facts / owner checklist

Edit `src/config/siteFacts.ts`:

- `demoVideoUrl`: public YouTube URL after recording. It must be a supported youtube.com watch or youtu.be URL.
- `canonicalUrl`: public origin, if deployed. The public page applies absolute social/canonical metadata when a valid HTTPS origin is supplied; checked-in image paths remain relative for portable test builds.
- `contactUrl`, `privacyUrl`, `termsUrl`: reviewed real links. Empty entries show a clear placeholder dialog.
- `judgeInstructions`: public download instructions. Never add a password, API key or private document to client configuration.
- `metrics`: real measurements plus dataset/date/context. Null/unexplained values stay hidden. Human judge calibration is not claimed complete.
- Repository links are configured, but the owner must ensure judges can access the repository/release.

## Manual QA checklist

- [ ] Fresh signed-out browser: public landing → sign-in → successful login → existing workspace.
- [ ] Signed-in refresh, logout, expired-session behavior and `/welcome` round trip.
- [ ] One real cited answer; source slide/page opens correctly; beyond-material label stays honest.
- [ ] Stop in Chat and each generating tool; received partials remain.
- [ ] Select two materials; save and reopen a study set; max-five rule remains.
- [ ] Overview, Tutor, Notes, Summary, Flashcards, Assessment, Progress and Study Plan.
- [ ] Memory edit/delete/undo; task completion; long-running plan cancel.
- [ ] Both themes at 360, 768, 1280 and your 2K monitor, including browser zoom.
- [ ] Keyboard-only menus/dialogs/FAQs and reduced-motion preference.
- [ ] Public demo video, policy/contact links and judge instructions after filling configuration.

No backend field, API or database changes are required. The existing server's SPA fallback supports the added public routes. This work does not fix or claim to validate model answer quality, long-summary length, human judge calibration or optional service credentials.

## Verification recorded for this change

- Production frontend build: passed.
- Existing frontend DOM/model tests: 90 passed.
- Judge packaging/secret-boundary checks: 5 passed.
- Public-page browser suite: 12 viewport/theme combinations passed, plus an animation-enabled lazy-section reveal check.
- Signed-in layout suite: 10 viewport/theme combinations passed, including all eight workspace tabs, five material selection, 2K/4K widths and 320px mobile.
- During implementation, local mobile Lighthouse measured Performance 96, Accessibility 100, Best Practices 96 and SEO 100; LCP about 2.34 seconds and CLS 0. Automated WCAG A/AA scans detected no violations on the corrected public page in either theme. These are local measurements, not guarantees for every device or a future host.
- The audit environment blocked Google Fonts, so fallbacks were used. Verify real font loading and layout shift on the deployed browser; this is also why Best Practices was below 100.
- Real provider generation, login with your credentials, Stop across live jobs, source-file previews and memory writes still need the manual smoke checks above. Layout fixtures do not replace live model/e2e verification.

Update the Docker test build from the project folder:

```powershell
git pull origin main
docker compose --env-file judge/.env.judge -f judge/compose.yaml up -d --build app
```

Then open `http://localhost:8888/welcome` and hard-refresh with Ctrl+Shift+R. The existing settings and data volumes are retained.
