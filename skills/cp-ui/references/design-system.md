# Design system — MASTER.md format and how to present it

`run.py --design-system` composes three directions; the operator decides; you write ONE
`MASTER.md` and record it. `uikit.parse_master` validates it; anything it rejects exits 1
with the list of problems.

## MASTER.md format

```markdown
# Design system — <product>

## Style
One short paragraph: the visual personality (required, non-empty).

## Colors
- primary: #1D4ED8
- on_primary: #FFFFFF
- background: #FFFFFF
- foreground: #111827

## Typography
- heading: Inter
- body: Inter

## Spacing        (optional)
## Motion         (optional)
## Anti-patterns  (optional)

## Decision
Chosen by: <the operator's name>
Alternatives shown: A, B, C
Why: <the operator's reason, in their words>
```

Rules:

- **Colors** are `- role: #RRGGBB` bullets, six-digit hex only (no `#fff`, no names, no rgb()).
  Allowed snake_case roles (16): `primary`, `on_primary`, `secondary`, `on_secondary`,
  `accent`, `on_accent`, `background`, `foreground`, `card`, `card_foreground`, `muted`,
  `muted_foreground`, `border`, `destructive`, `on_destructive`, `ring`. Any other role is
  rejected. Required: `primary`, `on_primary`, `background`, `foreground`.
- **Contrast** (WCAG 2, minimum 4.5:1) is checked for each pair that is present:
  `foreground` on `background`, `on_primary` on `primary`, `card_foreground` on `card`,
  `muted_foreground` on `background`.
- **Typography** needs both `heading` and `body` font names.
- **Decision** needs all three fields filled. `Chosen by` must equal `--chosen-by`
  (case-insensitive); the packet drafts leave them empty on purpose.

## Presenting the directions

1. Open the three HTML previews (paths in the packet) for the operator and show the
   directions **side by side**: style, primary/background, fonts.
2. **The operator picks, mixes or edits** (for example A's palette with B's fonts). Never
   choose for them and never fill `## Decision` yourself.
3. Ask **one question per message**: first which direction (or mix), then, if needed, one
   follow-up (a color to change, a font), then why.
4. If the packet says the directions come from the generic fallback query, ask for
   product-type / industry keywords and re-run before presenting.
5. Write the final document from the draft the operator settled on, with their name in
   `Chosen by`, the directions shown in `Alternatives shown`, their reason in `Why`.

## Recording

```
python scripts/run.py --design-system --record FILE|- --chosen-by NAME
```

Writes `.context/design-system/MASTER.md` and `tokens.json`, appends a
`## Design system — <product> (<date>)` entry to `.context/tracking/decisions.md`, and logs
an event. `--page NAME` writes `design-system/pages/<name>.md` only. Replacing an existing
file needs `--force --reason "..."`. Exit codes: 1 invalid document / mismatch / refused
overwrite, 4 not writable, 5 not authorized.
