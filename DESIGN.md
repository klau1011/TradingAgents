# Design System: Console (from Hallmark)

Adapted from the Console theme in [Hallmark](https://github.com/Nutlope/hallmark) (`skills/hallmark/references/themes/console.md`, MIT). The dashboard is dark only.

## 1. Visual Theme & Atmosphere

An instrument kept by careful people. A graphite ground stepped in three lightnesses, hairline panels cut from one surface, Host Grotesk for what a person reads, Atkinson Hyperlegible Mono for what an instrument measured. Amber marks a person, cool blue marks an instrument. Nothing glows: no shadows, gradients, textures or hover lifts. It is not a neon terminal, a glass dashboard or a science-fiction control room.

**Key Characteristics:**
- Graphite in three steps: page, panel, deepest band
- 1px hairline borders, 10px panels, 6px controls, 4px chips
- Host Grotesk 500 headings with -0.03em tracking, sentence case
- Mono only for figures: prices, P&L, dates, times, durations, IDs
- Two signals (amber, cool) plus ok/bad for status and gains/losses

## 2. Color Palette & Roles

Tokens live in `web/frontend/src/styles/tokens.css` as OKLCH channels and are exposed as Tailwind colors in `tailwind.config.ts`.

### Neutrals
| Tailwind | Token | OKLCH | Role |
|---|---|---|---|
| `canvas` | `--color-bg` | 17% 0.008 250 | Page ground |
| `surface` | `--color-surface` | 21% 0.009 250 | Panels (Card), table heads |
| `inverse` | `--color-inverse` | 13.5% 0.007 250 | Deepest step: hero bands, code, inputs |
| `fg` / `inverse-fg` | `--color-fg` | 95% 0.005 250 | Primary text |
| `muted` | `--color-muted` | 83% 0.008 250 | Secondary text, labels |
| `subtle` | `--color-subtle` | 71% 0.01 250 | Tertiary text |
| `edge` | `--color-border` | 31% 0.01 250 | Hairlines |
| `edge-strong` | `--color-border-strong` | 42% 0.012 250 | Control outlines, link underlines |

### Signals
| Tailwind | OKLCH | Meaning in this app |
|---|---|---|
| `accent` (`-ink`, `-soft`) | 82% 0.15 80 | A person or the current step: primary button, running agent, reconnecting warning, focus ring |
| `cool` (`-soft`) | 77% 0.12 245 | An instrument: timestamps, run IDs, report folder IDs, the chosen items in a picker (selected analysts) |
| `ok` (`-soft`) | 76% 0.15 150 | Done, BUY/overweight, positive alpha, API key present |
| `bad` (`-soft`) | 70% 0.17 25 | Error, SELL/underweight, negative alpha, cancel |

HOLD, queued and cancelled are neutral: no tint, a hairline outline only.

## 3. Typography Rules

### Font Families
- **Display and body**: Host Grotesk 400/500 (`font-display`, `font-body`)
- **Measured**: Atkinson Hyperlegible Mono 400/500 (`font-mono`)

Both load from Google Fonts in `web/frontend/index.html`.

### Hierarchy
| Tailwind | Size | Line height | Tracking | Use |
|---|---|---|---|---|
| `text-display-mega` | 8.5rem | 1.02 | -0.03em | Reserved |
| `text-display-hero` | 5rem | 1.04 | -0.03em | Page titles |
| `text-section` | 3rem | 1.04 | -0.03em | Section headings |
| `text-sub` | 2.5rem | 1.05 | -0.03em | Large readings (mono) |
| `text-card` | 2rem | 1.1 | -0.03em | Card titles |
| `text-feature` | 1.5rem | 1.33 | 0 | Small headings |
| `text-nav` | 1.25rem | 1.40 | 0 | Navigation, decision badge |
| `text-body-lg` | 1.125rem | 1.55 | 0 | Introductions |
| `text-body`, `text-body-em` | 1rem | 1.55 | 0 | Reading text, controls |

### Principles
- Headings are weight 500, never bold.
- Labels, table heads and chips are sentence case in Host Grotesk 500. No tracked capitals.
- Mono is for what an instrument or the system wrote. Never on a label, heading or button.

## 4. Component Stylings

### Buttons (`components/ui/Button.tsx`)
All buttons: Host Grotesk 500 at 1rem, 6px radius, 1px border, 10px 20px padding, hover opacity 0.85, amber focus ring.
- **primary**: amber fill, `accent-ink` text. One per view.
- **secondary / ghost**: `surface` fill, `edge-strong` outline. Ghost is for the deep hero bands.
- **outlined**: transparent, `edge-strong` outline.
- **danger**: `bad-soft` fill, `bad` text.

### Chips (`components/ui/StatusBadge.tsx`)
State only. 4px radius, 1px `edge` rule, tinted `-soft` by meaning, no status dot. The decision badge uses the same rule at 6px and `text-nav` size; a preview adds a muted "Preview" label rather than lowering opacity.

### Cards & Containers
- `Card`: `surface` fill, 1px `edge` border, 10px radius, sitting on the `canvas` ground.
- Hero bands use `inverse`, the deepest step. At most two bands a page.
- Tinted alerts (warning, error) are plain sections, not `Card`: Tailwind sorts color utilities alphabetically, so Card's base classes would override the tint.

### Inputs
`inverse` fill, 1px `subtle` border (a field edge needs 3:1 against the panel), 6px radius. The border never changes; focus is the amber outline.

### Focus
Every focusable element gets a 2px amber `:focus-visible` outline, instant (`tokens.css`). Buttons use the `shadow-focus` ring instead.

### Links
Text color with an `edge-strong` underline; amber on hover.

### Report prose
`.md-body` paragraphs, list items and quotes cap at 72ch; tables keep the full width.

## 5. Layout Principles

### Spacing System
- Base unit: 8px
- Custom steps: 14px, 32px, 34px, 80px, 88px, 120px
- Large section spacing: 80px

### Border Radius Scale
- `rounded-chip` (4px): status chips, inline code
- `rounded-sm` / `rounded-pill` (6px): inputs, buttons, toggles. `pill` keeps its old name.
- `rounded-card` (10px): panels, code blocks

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Ground | `canvas` | Page |
| Panel | `surface` + 1px `edge` | Cards, report boxes |
| Deep | `inverse` | Hero bands, code, inputs |
| Focus | `0 0 0 2px` amber ring | Keyboard focus |

No shadows. Depth comes from the three graphite steps and hairlines.

## 7. Do's and Don'ts

### Do
- Keep amber for people and the current step, cool for instruments
- Set every figure in mono so columns line up
- Use 1px hairlines and the three graphite steps for structure

### Don't
- Don't swap the meanings: no amber readings, no cool warnings
- Don't add shadows, glows, gradients or a third signal color
- Don't use mono on labels, headings or buttons
- Don't use uppercase tracked labels

## 8. Responsive Behavior

### Breakpoints
Tailwind defaults: `md` 768px, `lg` 1024px.

## 9. Agent Prompt Guide

### Quick Color Reference
- Ground: `bg-canvas`; panel: `bg-surface border border-edge`; deep: `bg-inverse`
- Text: `text-fg`, `text-muted`, `text-subtle`
- Person / current step: `accent`; instrument: `cool`; status: `ok`, `bad`

### Example Component Prompts
- "Add a stat: label in `font-display text-nav text-muted`, value in `font-mono text-sub`, hint in `text-body-em text-muted`."
- "Add a status chip: `rounded-chip border border-edge px-3 py-1 font-display font-medium` plus `bg-ok-soft text-ok`."

### Iteration Guide
1. Host Grotesk 500 for headings, never bold
2. Mono for figures only
3. Amber is a person, cool is an instrument
4. No shadows; hairlines and graphite steps only
