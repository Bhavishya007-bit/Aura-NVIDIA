# Responsive chat and study workspace

The reported 2K screenshot showed a 740px chat shell, fixed 15px teaching text and large unused margins. Authentication is retained; this update changes presentation only.

## Layout changes

`src/layout.css`, imported last in `src/main.tsx`, defines viewport tokens shared by Chat home and the Study workspace:

- Chat uses a fluid width with a 1312px upper limit instead of the fixed 740px cap. Answers have their own 1040px reading limit, keeping tables and code useful without stretching prose across the entire monitor.
- Answer/input text scales from 16px to 18px. Large-desktop headings, navigation and material labels have clearer sizing. Existing light/dark colours are preserved.
- Wide study workspaces use a larger content area and proportionate navigation/material columns. Child grid/flex tracks can shrink; code and tables scroll inside their containers.
- Narrow headers wrap, account names truncate, and material chips remain removable. Expanded material lists and multiple selection chips have bounded scrolling areas so they leave room for the conversation and composer.
- The workspace Tutor uses a column layout on mobile while preserving its existing materials drawer and Escape-to-close behaviour.
- Below 560px viewport height, the page permits vertical scrolling rather than clipping the composer behind a fixed-height frame. Safe-area padding is retained for mobile input.

No authentication, API route, payload, database field, generation/cancellation logic or saved-content format changes. No production dependencies were added.

## Browser verification

`scripts/check_responsive.mjs` opens the actual compiled frontend in Chromium. Synthetic API responses and browser-local history are injected **only inside the test browser context**; these are authored layout fixtures, not live model outputs. It also opens a separate signed-out context to confirm that the authentication page remains. Existing public container smoke checks independently verify real anonymous API rejection.

The script checks Chat and all eight workspace tabs at 3840×2160, 2560×1440, 1920×1080, 1280×800, 768×1024, 390×844, 320×700 and 640×360. It repeats desktop/phone checks for the dark workspace theme. Assertions cover wide-screen content width and type size, horizontal overflow, composer visibility/reachability, all five selected materials, keyboard focus and the mobile materials drawer. Long prose, code and a table are included. Screenshots and measurements are saved to the test output directory.

To run against an already running local build or container, with test-only Playwright available:

```bash
AURA_UI_TEST_MODULES=/path/to/test/node_modules node scripts/check_responsive.mjs http://localhost:8888
```

The Production and Judge build workflows install Playwright as a test-only tool, run this check after the signed-out smoke check, and retain screenshots/measurement reports as workflow artifacts. Browser checks assess layout using controlled data, not model accuracy or live generation latency.

## Update the local Docker app

From the Aura repository root, with Docker Desktop running:

```powershell
git pull origin main
docker compose --env-file judge/.env.judge -f judge/compose.yaml up -d --build app
```

Open http://localhost:8888 and use Ctrl+Shift+R if the browser retains old CSS. Existing accounts, API settings, selected materials and saved work remain in place. Browser zoom and operating-system display scaling can change the effective CSS viewport; the layout responds to the available browser space.
