# Static checks

`run.py --audit` lists regex *candidates* from these rules over html, css, scss, jsx, tsx,
vue, svelte and astro files. A hit is a lead: open the file, decide, and answer
`confirmed`, `dismissed — <reason>` (hidden from future packets) or `cannot verify — <why>`.
To dismiss a false positive record `Verdict: dismissed — <reason>` for it; the dismissal is
keyed by rule, file and the line's text, so it returns if that line changes.

### raw-color
Flags: a hex, `rgb()`/`hsl()` colour literal in a UI file (only when a design system exists;
token files and `--var:` definitions are skipped). Why: literals drift from the design system
and break theming/dark mode. Fix: use the token or CSS variable. False positives: brand
logos or illustrations that must keep exact colours, third-party embeds, a token file with an
unusual name — dismiss with the reason.

### img-no-alt
Flags: an `<img>` with no `alt`. Why: screen readers read the file name instead. Fix: a
meaningful `alt`, or `alt=""` for a purely decorative image. False positives: a component
that injects `alt` through spread props (`{...props}`) — dismiss after checking it.

### icon-button-no-name
Flags: a `<button>` whose only content is an icon element with no `aria-label`, `title` or
visually hidden text. Why: assistive tech announces just "button". Fix: add `aria-label`
or an `sr-only` span. False positives: a label supplied by a wrapper component or
`aria-labelledby` elsewhere — dismiss after checking.

### outline-removed
Flags: `outline: none/0` or `outline-none` without a visible `:focus`/`focus-visible`
replacement on the same line. Why: keyboard users lose track of focus. Fix: replace it with
a ring, shadow or outline under `:focus-visible`. False positives: the replacement lives on
another line or in a shared class — dismiss and name where.

### zoom-disabled
Flags: a viewport meta with `user-scalable=no` or `maximum-scale=1`. Why: blocks pinch-zoom
and text scaling for low-vision users. Fix: remove those parts. False positives: almost
none; a kiosk or game canvas with an alternative zoom — dismiss with that reason.

### missing-lang
Flags: an `<html>` tag without `lang`. Why: screen readers pick the wrong voice and
pronunciation. Fix: `<html lang="pt-BR">` (or the real language). False positives: an HTML
fragment/template whose layout sets `lang` — dismiss.

### missing-viewport
Flags: an HTML document without a viewport meta tag. Why: mobile browsers render a desktop
canvas, shrunk. Fix: `<meta name="viewport" content="width=device-width, initial-scale=1">`.
False positives: a partial or email template; a layout that adds the tag at build time.

### tiny-font
Flags: a font size under 12 px (`font-size: 11px`, `text-[10px]`). Why: unreadable for many
users and hard on mobile. Fix: 14-16 px for body text, 12 px as the floor for captions.
False positives: a deliberately small legal footnote or a badge counter — dismiss with the reason.

### emoji-icon
Flags: an emoji used as the icon of a button, link or nav item. Why: emojis render
differently per platform, do not follow the theme and are announced awkwardly. Fix: use an
SVG icon from the project's icon set. False positives: an emoji that is itself the content
(a reaction picker, a user message) — dismiss.

### no-reduced-motion
Flags: the project animates (keyframes, `animation:`, `animate-*`, a motion library) but no
file honours `prefers-reduced-motion`. Why: motion can trigger vestibular problems. Fix: a
`@media (prefers-reduced-motion: reduce)` rule, `motion-reduce:` utilities or
`useReducedMotion`. False positives: handled in a file outside the scan (a global stylesheet
under an `exclude`) — dismiss and name it.

## Visual rules (`visual:<check>`)

Come from the optional visual audit (see SKILL.md). Location is `<viewport> <selector>`;
a confirmed visual finding is grouped into one BUG per `visual:<check>` and viewport
(key `visual:<check>::<viewport>`, the viewport playing the role of the file).
