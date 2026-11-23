# NetAudio Monitor mockup

A clickable mockup built with [shadcn/ui](https://ui.shadcn.com) (zinc, Inter and JetBrains Mono). It is a design reference for the real app (native C++ with Dear ImGui, for Windows and Linux), and is not part of it. All data is sample data.

![levels](screenshots/levels.png)

![flows](screenshots/flows.png)

![settings](screenshots/settings.png)

## Screens

| Route | Screen | What it shows |
|---|---|---|
| `#/levels` | Levels | Device cards, stat cards, filter chips, stereo pairs, docked listen bar |
| `#/flows` | Flows | Every multicast, AES67 and unicast flow |
| `#/clock` | Clock | Read-only PTP status |
| `#/settings` | Settings | Network, audio, meters, daemon |
| `#/about` | About | Credits and trademark notice |

Dark only, as in the spec. The theme switch is hidden. Below 768 px it switches to the phone layout, where the sidebar becomes a sheet; `phone-*.png` in `screenshots/` shows it.

## Run it

```bash
cd docs/mockup
npm install
npm run dev          # http://localhost:5173
npm run build        # production build in dist/
npm run typecheck
```

## Screenshots

`shots.json` lists the screenshots (route, theme, size). To retake them:

```bash
npm install
npx playwright install chromium
npm run build
npm run screenshots  # writes screenshots/*.png
```

## Layout

The project has the same shape in every repo, so a change to the frame can be copied across.

| Path | |
|---|---|
| `src/components/ui/` | shadcn/ui components (MIT), added with `npx shadcn@latest add <name>`; `components.json` is already set up |
| `src/components/` | Shared pieces: `app-shell` (sidebar, header, breadcrumb), `page-header`, `stat-card`, `status-pill`, `level-meter`, `filter-chips`, `listen-bar`, `theme-toggle` |
| `src/index.css` | shadcn zinc tokens (light and dark) plus `success` and `warning` |
| `src/App.tsx` | Nav, sidebar status and routing for this product |
| `src/screens/` | One file per screen |
| `src/data.ts` | Sample data (where the screens share any) |
| `shots.json`, `scripts/screenshots.mjs` | Screenshot list and script |

Everything under `src/components/`, `src/lib/`, `src/hooks/`, `src/index.css` and `scripts/` is identical across the four repos. Keep it that way: change one, copy to the others.

The mockup is React because shadcn/ui is. The real UIs are not: use the matching library there ([shadcn-svelte](https://shadcn-svelte.com) for the Svelte web UIs) and the mockup's tokens and layout.
