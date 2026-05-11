# Frontend Redesign Notes - Pass 2

## Component Summary

- Upload: added drag-over accent state, processing pulse, image/PDF previews, upload/OCR/review/confirm/discard status text, and non-blocking toast notifications for success, discard, and network failures.
- Transactions: upgraded the table into a data-grid with sticky headers, fixed date/amount/status columns, token-colored status chips, keyboard-expandable rows, animated detail panels, and existing inline resolve/dismiss API actions.
- Charts: applied token colors to series, axes, grids, and legends; added `ResizeObserver` plus resize scheduling; rendered empty states instead of empty datasets; added CSS-only chart entrance animation.
- Nova Chat: added structured user/assistant bubbles, timestamps, copy buttons, typing indicator, streaming cursor, stop button backed by `connection.close()`, retry affordance, and idle/connected/error status indicator without changing the SSE endpoint or event format.
- Accessibility: added live regions, chat log semantics, keyboard row expansion, keyboard drop-zone activation, sort buttons in table headers, visible focus rings, chart labels, field error relationships, and WCAG AA token contrast validation.

## Token Usage Map

- Surface/layout: `--background`, `--surface`, `--surface-muted`, `--surface-subtle`, `--surface-accent-soft`, `--border`.
- Status and feedback: `--accent`, `--success`, `--warning`, `--error`, `--duplicate`.
- Charts: `--chart-1` through `--chart-6`, plus `--muted` and `--border` for axes/grid lines.
- Spacing: `--space-xs` through `--space-xl` for previews, table cells, details panels, chat controls, toasts, and empty states.
- Typography: `--text-sm` through `--text-xl`, `--font-weight-medium`, `--font-weight-bold`, and explicit line-height tokens.
- Shape/layers: `--radius-sm`, `--radius-md`, `--border-width-*`, `--z-table-header`, `--z-nova`.

## Accessibility Audit Results

- Automated Playwright checks verify landmarks, live regions, sort buttons, keyboard row expansion, and both dark/light theme contrast.
- Contrast ratios checked against `--surface`: dark minimum is `6.65:1` (`--error`); light minimum is `4.97:1` (`--text-secondary`). All checked foreground tokens meet WCAG AA normal-text threshold.
- Keyboard paths tested: sidebar/theme controls, table sort buttons, transaction row expansion with Enter, upload drop-zone activation, Nova send/stop/retry controls, and message copy buttons.
- Live announcements: upload status, preview strip, toast container, Nova connection state, typing state, and chat log.

## Verification History

- Task 1 upload gate: `npm test` passed with 51 backend tests and 11 Playwright tests.
- Task 2 table gate: `npm test` passed with 51 backend tests and 12 Playwright tests.
- Task 3 chart gate: `npm test` passed with 51 backend tests and 13 Playwright tests.
- Task 4 Nova gate: `npm test` passed with 51 backend tests and 14 Playwright tests.
- Task 5 accessibility gate: `npm test` passed with 51 backend tests and 16 Playwright tests.

Regression coverage confirms upload flow, Nova SSE stream behavior, and chart rendering stayed green after every task.

## Commits

- `93c1677` - `feat(upload): drag-and-drop zone, previews, progress states, toasts`
- `c279bb5` - `feat(table): data-grid styling, status chips, row expansion`
- `33d0bfa` - `feat(charts): token colors, responsive resize, empty states, entrance animation`
- `6c3e94a` - `feat(chat): streaming bubbles, typing indicator, stop button, connection status`
- `c909462` - `feat(a11y): semantic HTML, ARIA labels, keyboard nav, contrast verified`

## Known Limitations / Deferred Items

- The upload progress state reflects frontend request lifecycle; backend OCR still returns as one HTTP response, so there is no byte-level or OCR-stage progress percentage yet.
- Chart empty-state icons are CSS-only to preserve the vanilla frontend and avoid adding visual dependencies.
- Chat copy feedback is local to the button text and does not create an additional toast to avoid over-announcing screen reader output.
- The transaction detail expansion is table-row based to preserve existing DOM/API behavior; a future virtualized grid would be a larger architecture change.

## Push Status

All five Pass 2 task commits were pushed to `main` on `origin`.
