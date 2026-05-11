# Frontend Modularization Notes

Date: 2026-05-11

## Modules Created

- `frontend/api.js`: JSON API helpers and Nova SSE stream parsing. No DOM access.
- `frontend/state.js`: shared application state and sort helpers. No DOM access.
- `frontend/ui_components.js`: DOM construction helpers for rows, details, previews, bubbles, and buttons.
- `frontend/charts.js`: Chart.js lifecycle, resize handling, clearing, and degraded chart error state.
- `frontend/chat.js`: Nova form lifecycle, SSE token streaming updates, and graceful chat failure state.
- `frontend/upload.js`: upload preview, extraction review, confirm/discard flow, and inline validation.
- `frontend/main.js`: dashboard entry point, transaction rendering, sorting, refresh wiring, and analysis update events.

`frontend/index.html` now loads the ES module entry points with `type="module"`. Existing DOM IDs, existing selector class names, API routes, and SSE `data:` parsing behavior were preserved.

## Circular Dependency Check

Static imports are intentionally shallow:

- `chat.js` imports `api.js` and `ui_components.js`.
- `main.js` imports `api.js` and `ui_components.js`.
- `upload.js` imports `api.js` and `ui_components.js`.
- `api.js`, `state.js`, `ui_components.js`, and `charts.js` have no static imports.

No module imports from more than two other modules. No circular import path is present.

## CSS Tokens

`frontend/style.css` now defines tokens for:

- Colors: background, surface, border, text-primary, text-secondary, accent, success, warning, error.
- Spacing: `--space-xs` through `--space-xl`.
- Typography: `--text-sm` through `--text-xl`, plus normal/medium/bold font weight tokens.
- Radius, border-width, and shadow tokens.

Token values match the prior hardcoded values, so this pass does not intentionally change visible styling.

## InnerHTML Replacements

Removed unsafe `innerHTML` usage from frontend source. The following surfaces now use safe DOM construction and `textContent`:

- Transaction table rows with merchant/category/API data.
- Transaction detail rows with bill number, payment method, and line items.
- Extraction preview fields with OCR output and user-editable values.
- Preview/table/extraction clearing now uses `replaceChildren()`.

Current check: `rg -n "innerHTML" frontend` returns no matches.

## Security And Resilience Changes

- API/OCR/user-edited values are rendered as text, not markup.
- Upload confirmation validates merchant, total/subtotal/tax numeric fields, date format, and category when a category input is present.
- Inline field errors use `[data-field-error]` and `aria-invalid`; no alerts were introduced.
- Upload, confirm, discard, Nova SSE, and chart rendering failures degrade to visible UI messages instead of unhandled page crashes.
- Chart rendering failures show `Charts are temporarily unavailable.` inside chart boxes.

## Deferred Items

- A visible category edit field was not added because the existing extraction preview did not expose one, and adding a new row would change the protected layout. The validation path supports `category` when that input exists.
- Actual separate commits were not created because this workspace is not a git repository (`git status` reports no `.git` directory).
