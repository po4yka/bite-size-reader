---
version: alpha
name: Frost
description: >
  Editorial monospace minimalism for Ratatoskr. Two-color rule (ink + page) with
  a single critical accent (spark), eight-step alpha ladder, signal ramp, and
  brutalist component architecture (1px hairline, 0 corner radius, no shadow).
  This file is the web-platform projection of the canonical Frost design system
  maintained in Figma file `dvCkDlNR6CKgfekPgrWo87` and exported as
  `frost-tokens.json` (DTCG format, currently v2.13.0).
colors:
  ink: "#1C242C"
  ink-dark: "#E8ECF0"
  page: "#F0F2F5"
  page-dark: "#12161C"
  spark: "#DC3545"
  ink-pure: "#000000"
  page-pure: "#FFFFFF"
typography:
  mono-xs:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: 500
    lineHeight: 130%
    letterSpacing: 1px
  mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: 500
    lineHeight: 130%
    letterSpacing: 0.4px
  mono-body:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: 500
    lineHeight: 130%
    letterSpacing: 0.4px
  mono-emph:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: 800
    lineHeight: 130%
    letterSpacing: 1px
  serif-reader:
    fontFamily: Source Serif 4
    fontSize: 16px
    fontWeight: 500
    lineHeight: 155%
    letterSpacing: 0px
    fontFeature: italic
  serif-reader-zoom:
    fontFamily: Source Serif 4
    fontSize: 22px
    fontWeight: 500
    lineHeight: 155%
    letterSpacing: 0px
    fontFeature: italic
rounded:
  none: 0px
spacing:
  cell: 8px
  half-line: 8px
  line: 16px
  gap-inline: 4px
  gap-row: 8px
  gap-section: 48px
  gap-page: 64px
  pad-page: 32px
  strip-1: 176px
  strip-2: 352px
  strip-3: 528px
  strip-4: 704px
  strip-5: 880px
  strip-6: 1056px
  strip-7: 1232px
  strip-8: 1408px
components:
  brutalist-card:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    typography: "{typography.mono-body}"
    rounded: "{rounded.none}"
    padding: "{spacing.line}"
  brutalist-card-critical:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    typography: "{typography.mono-emph}"
    rounded: "{rounded.none}"
    padding: "{spacing.line}"
  pull-quote:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    typography: "{typography.serif-reader-zoom}"
    rounded: "{rounded.none}"
    padding: "{spacing.line}"
  bracket-button:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    typography: "{typography.mono-emph}"
    rounded: "{rounded.none}"
    padding: 8px 16px
  status-badge:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    typography: "{typography.mono-xs}"
    rounded: "{rounded.none}"
    padding: 4px 8px
  mark:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ink}"
    typography: "{typography.mono-body}"
    rounded: "{rounded.none}"
    padding: 0 2px
---

## Overview

Frost is the project-owned design system for Ratatoskr — an editorial
news-aggregation product. It is intentionally **post-Carbon**: the legacy
`--rtk-*` token shim in `clients/web/src/design/tokens.css` carries
seed values from the previous IBM Carbon theme so the codemod removing
the old design system stayed mechanical. Migrating those tokens to
Frost values is in-progress; this DESIGN.md is the migration target.

Frost's three principles:

1. **Two-color rule.** Ink and page invert in dark mode; nothing else
   changes color. The only chromatic value is `spark` (`#DC3545`),
   reserved for critical-signal accents (a 2px leading hairline on web,
   4px on mobile). Spark stays the same in both modes — it is a
   physical pigment, not a UI affordance.
2. **Brutalism.** 0 corner radius, 1px hairline borders only, no
   shadows, no gradients. Cards are slabs. Buttons are bracketed
   monospace text. The medium is the message.
3. **Signal-driven hierarchy.** Every row, heading, and toast picks one
   of four signal levels (low / mid / high / critical). Signal maps to
   weight + alpha + case, not to color. Color is reserved for one job:
   marking a row as fatal.

The Figma source-of-truth lives at file id `dvCkDlNR6CKgfekPgrWo87`
(19 pages: 01 Cover, 02 Philosophy & Anti-Patterns, 03 Color & Alpha,
04 Type, 05 Grid & Spacing, 06 Signal Ramp, 07 Motion, 08 Atoms,
09 Molecules, 10 Layout Templates, 11 Web Views, 12 Mobile Views,
13 Keyboard Map, 14 Annotations & Specimens, 15 Icons, 16 Localization,
17 Semantic Tokens, 18 Charts & Graphs, 99 Changelog).

## Colors

Two-color rule: light mode is `ink: #1C242C` on `page: #F0F2F5`;
dark mode flips to `ink: #E8ECF0` on `page: #12161C`. Spark
(`#DC3545`) never flips. `ink-pure` and `page-pure` exist for
print/PDF export only — never for UI.

Color is **forbidden** as a hierarchy device. To express depth or
emphasis, vary the alpha applied to ink (eight-step ladder):

| Token         | Value | Use                                                    |
|---------------|-------|--------------------------------------------------------|
| `quiet`       | 0.25  | Watermarks, decoration only — fails AA, never carry text |
| `dot`         | 0.40  | Separator dots, dotted/dashed borders                  |
| `inactive`    | 0.50  | Inactive filter buttons                                |
| `low-signal`  | 0.55  | Low-signal text (signal score < 0.3)                   |
| `meta`        | 0.60  | Timestamps, secondary meta                             |
| `secondary`   | 0.70  | Section headings, ingest line                          |
| `active-soft` | 0.85  | Hover-out, dense secondary, body in compact rows       |
| `active`      | 1.00  | Active text, mid/high/critical signal                  |

WCAG verdicts are pinned on Figma page 02 (Contrast Verdict). Active
and active-soft pass AAA in both modes. Quiet fails AA — it is a
decoration token, never a text token.

## Typography

Two families:

- **JetBrains Mono** — every UI surface (labels, body, meta, headings,
  status, code). Three weights: thin 400 (low signal), body 500
  (default), emph 800 (uppercase headings, critical state).
- **Source Serif 4 italic** — reader body only. Used for the article
  reading view and pull-quotes. Never for UI chrome.

Tracking is treated as a tunable: `tight` (0.3px) for mobile body,
`body` (0.4px) default, `label` (1px) for UPPERCASE labels and nav,
`wide` (1.5px) for stronger uppercase, `wordmark` (2px) for the
wordmark and section heads.

Line-height is one of three percentages: `tight` 115% (ultra-dense
rows), `body` 130% (default), `reader` 155% (Source Serif italic).

The font shim in `clients/web/src/design/tokens.css` currently
references generic `--rtk-font-body-01-size`. Migrate consumers to
the JetBrains Mono / Source Serif tokens above.

## Layout

The grid is **cellular**, not column-based. The cell is `8px`. On
web (`1440px` viewport baseline) the page is 178 cells wide. On
mobile (`393px` artboard baseline) the page is ~48 cells wide. The
tablet range (768–1199px) uses web tokens; below 768px the mobile
artboard takes over.

Vertical rhythm is `line: 16px` (2 cells). Section gaps are
`gap-section: 48px` (6 cells). Page-level rhythm is
`gap-page: 64px` (8 cells). Page horizontal padding is
`pad-page: 32px` (4 cells).

Content columns snap to one of eight `strip-N` widths from
`strip-1: 176px` to `strip-8: 1408px` (the maximum content
column). A web view is composed of strips placed at integer
cell offsets from the page edge.

Breakpoints:

| Token   | Value    | Notes                                       |
|---------|----------|---------------------------------------------|
| mobile  | 393px    | Mobile artboard, 48-col grid                |
| tablet  | 1024px   | Tablet — uses web tokens                    |
| web     | 1440px   | Web baseline, 178-col grid                  |

## Shapes

`rounded.none = 0px` is the only radius token. There is no `sm`,
`md`, `lg`. Cards, buttons, badges, inputs — every container — has
a square corner. This is enforced by the **§6 Brutalism** principle
documented on Figma page 02. If a component needs to feel softer,
the answer is more whitespace, not more radius.

Borders are 1px hairline ink-bound at alpha 0.40 (`dot`) for
separators, 0.50 (`inactive`) for row dividers, 1.00 (`active`) for
keyboard focus. The single exception is the **spark bar** — a 2px
leading edge on web (4px on mobile) painted in `spark`, signalling
critical state.

There are no shadows. There are no gradients. There is no glassmorphism.

## Components

Composition is **cards over canvas**: every cluster of related
information is a Brutalist-Card, separated from siblings by a single
hairline divider. Cards never overlap, never round, never shadow.

The web canon set lives in Figma pages 08 (Atoms) and 09 (Molecules).
Selected anchors:

- **Brutalist-Card** — slab card. State enum: `default | critical`.
  Critical adds a 2px leading spark hairline.
- **Pull-Quote** — Source Serif 4 medium italic body, mono uppercase
  attribution. Used for editorial highlights and quote-of-the-week.
- **Bracket-Button** — `[ LABEL ]` literal brackets, mono ExtraBold
  uppercase. The brackets are characters, not background fills.
- **Status-Badge** — pill-shaped mono uppercase, severity enum
  `info | warn | alarm`. Alarm adds the spark bar; alarm never paints
  text red.
- **Atom / Mark** — inline text-highlight (added v2.13.0). Wraps a
  span of body text with `ink/0.08` alpha background + 1px ink/0.4
  underline. HUG-sized. Variants: `style=match | passage`.
- **Chip** — bracket-bordered uppercase mono label, used for filters
  and the version index.
- **Row / Digest** — single-row card composed of mono cells, used in
  list views.

Web views are assembled from these components in
`clients/web/src/design/`. When a new view is needed, prefer
composing from existing primitives over inventing new ones.

## Do's and Don'ts

**Do**

- Use ink + alpha for hierarchy. A heading is `weight 800 + alpha
  1.00 + uppercase`, not a different color.
- Reserve spark for fatal/critical states only. If you reach for
  spark, ask whether the row is genuinely a failure.
- Pick a signal level (`low | mid | high | critical`) for every
  text node. Picking is mandatory; defaulting is a defect.
- Snap content widths to `strip-N` tokens. Arbitrary widths break
  the cell grid and cause off-by-cell drift.
- Validate WCAG against the alpha ladder before introducing new
  text usage. The ladder verdicts are pinned on page 02.

**Don't**

- Don't use color for hierarchy. Blues, greens, ambers do not exist
  in Frost. The legacy `#0F62FE` interactive blue and `#24A148`
  success green still present in `tokens.css` and `AppColors.kt`
  are migration debt; new code must not bind to them.
- Don't add corner radius. `rounded-md`, `border-radius: 8px`,
  `RoundedCornerShape(...)` — all defects in this codebase.
- Don't add shadows or gradients. Depth comes from typography
  weight and the alpha ladder, not from blur.
- Don't paint text in spark. Critical state is a 2px leading hairline
  in spark, not red text. Red text is a banned anti-pattern.
- Don't use Inter, Roboto, Arial, or Helvetica. Mono is JetBrains
  Mono; serif is Source Serif 4 italic. No substitutions.
- Don't introduce new motion. Frost has seven permitted animations
  (`blinker`, `pulse`, `toast`, `click-press`, `select-pulse`,
  `drag-lift`, `undo-fade`). All collapse to 1ms under
  `prefers-reduced-motion`.

## References

- Canonical tokens: `frost-tokens.json` (DTCG, repo root of the
  Frost project; tracked separately from this repo).
- Figma source: file id `dvCkDlNR6CKgfekPgrWo87`.
- Web tokens shim (legacy, pending migration):
  `clients/web/src/design/tokens.css`.
- Web design primitives: `clients/web/src/design/`.
- This file documents Frost as it should land in this repo. Where
  this file and the code disagree, this file is the target.
