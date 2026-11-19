# UI audit checklist

Seven checks a regex cannot make. Answer each with `ok`, `finding`, `not-applicable` or
`not-verified`, plus the **evidence** (what you ran, saw or read). No evidence means
`not-verified` — never `ok`. A `finding` also needs a `## Finding` block with
`Rule: checklist:<item-id>`. Adapted from the UI/UX Pro Max rules (pro-rules, quick-reference).

### states-loading-empty-error
Check: every screen or component that fetches data has a visible loading state, an empty
state that says what to do next, and an error state with a retry; none shows a blank area,
a raw stack trace or a spinner that never ends.
Evidence: the code branches that render each state (file:line), or a screenshot of each
state; "it loads fast" is not evidence.

### width-360
Check: at a 360 px wide viewport nothing scrolls horizontally, text is not clipped, tables
and long words wrap or scroll inside their own container, and the main action stays reachable.
Evidence: a screenshot at 360 px, or the layout rules (breakpoints, min-width, overflow) you
read for each main screen.

### keyboard-main-flow
Check: the main user flow can be completed with the keyboard alone: logical tab order that
matches the visual order, every control reachable and operable (Enter/Space), dialogs trap
and restore focus, Esc closes overlays, no keyboard trap.
Evidence: the sequence of keys you pressed and where focus went, or the handlers and
`tabindex` usage read in code.

### dark-mode
Check: if the product has a dark theme, text keeps at least 4.5:1 contrast (3:1 for large
text and UI parts), focus/disabled/pressed states stay distinguishable, and no surface is
hard-coded light. Without a dark theme, answer `not-applicable`.
Evidence: contrast ratios of the main text/background pairs in dark, or a screenshot of the
main screens in dark; the token or media-query definitions.

### touch-targets
Check: interactive elements are at least 44x44 px (48 dp on Android) including padding, with
at least 8 px between neighbours; small icons get an expanded hit area.
Evidence: the measured or computed size of the smallest controls (icon buttons, close
buttons, checkboxes, links in dense lists), from DevTools or the CSS you read.

### form-errors-inline
Check: validation errors appear next to the field (text, not colour alone), are tied to the
input (`aria-describedby`), say how to fix it, keep what the user typed, and a form with
several errors moves focus to an error summary or the first invalid field.
Evidence: the markup/handlers that render the message (file:line), or a screenshot of a
failed submit.

### focus-visible
Check: every interactive element shows a clearly visible focus indicator (at least 2 px or
3:1 contrast against its surroundings) on keyboard focus, in light and dark, and sticky
headers or overlays do not hide the focused element.
Evidence: a screenshot of the focused state of a button, a link and an input, or the
`:focus-visible` rules read; the static `outline-removed` candidates are a hint, not a proof.
