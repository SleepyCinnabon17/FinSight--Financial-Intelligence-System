# Pass 1 Layout Notes

Date: 2026-05-11

## Scope

Pass 1 covered layout structure and theming only. Existing backend API contracts, frontend module boundaries, exported function signatures, protected DOM IDs, protected data attributes, and SSE `data:` stream parsing hookpoints were preserved.

## Breakpoints Tested

- Mobile: 375px viewport, sidebar hidden behind `#sidebar-toggle`, opens with `.sidebar.is-open`.
- Tablet: 768px viewport, sidebar, KPI cards, main shell, and Nova panel remain visible and usable.
- Desktop: 1280px viewport, two-column shell, sidebar nav, KPI cards, and collapsible Nova panel are present.

These are covered by `tests/frontend/layout_pass1.spec.mjs`.

## Theme Toggle

- Default theme is dark via `html[data-theme="dark"]`.
- `.theme-toggle` switches between dark and light themes.
- Theme preference persists in `localStorage` under `finsight-theme`.
- Chart colors are read from CSS token values and re-rendered after theme changes.

## Selector Safety

- Existing JS selectors were preserved:
  - `#file-input`
  - `#file-picker-button`
  - `#drop-zone`
  - `#preview-strip`
  - `#upload-status`
  - `#extraction-preview`
  - `#transaction-body`
  - `#refresh-data`
  - `#chat-form`
  - `#chat-input`
  - `#chat-bubbles`
  - `#transaction-table th`
- No protected data attributes were renamed or removed.
- Module imports remain shallow; no module imports from more than two others.

## Test Results

Full suite was run after each task:

- Task 1 layout shell: `51 passed` Python tests, `6 passed` Playwright tests.
- Task 2 theme toggle: `51 passed` Python tests, `7 passed` Playwright tests.
- Task 3 typography/spacing tokens: `51 passed` Python tests, `7 passed` Playwright tests.
- Task 4 skeleton/empty states: `51 passed` Python tests, `8 passed` Playwright tests.

Final run after adding the tablet breakpoint test: `51 passed` Python tests, `9 passed` Playwright tests.

## Commits

- `feat(layout): responsive two-column shell, sidebar nav, KPI cards`
- `feat(theme): dark/light theme toggle with localStorage persistence`
- `style(tokens): apply typography and spacing tokens sitewide`
- `feat(ux): skeleton loaders and empty states for all major panels`

Branch target: `origin redesign/pass1-layout`.
