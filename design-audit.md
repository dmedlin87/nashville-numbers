# Design Audit: Nashville Numbers GUI

**Date:** 2026-03-07
**Scope:** `src/nashville_numbers/gui.py` — embedded single-file SPA
**Auditor:** Claude (Cowork)

---

## Overall Impression

A well-crafted, visually cohesive dark-mode SPA with a clear identity. The purple accent palette, glowing borders, and starfield background create a distinctive "music studio" vibe. The biggest opportunity is taming density and cognitive load — the UI packs a converter, a graphical builder, a fretboard visualizer, a full arrangement timeline, and an audio engine into a single scrolling page, which risks overwhelming new users.

---

## Usability

| Finding | Severity | Recommendation |
|---------|----------|----------------|
| Builder mode requires a two-step note + quality selection before a chord commits, but there's no visible "staged chord" preview — the intermediate state is unclear | 🟡 Moderate | Show a live preview of the staged note (e.g. "C + ?" chip in the progression track) so users know something is pending |
| The "Text" vs "Builder" tab toggle looks like a navigation element, not a mode switch for the same input field | 🟡 Moderate | Add a brief subtitle under the tabs or a tooltip: "Type chords directly" / "Build chords by clicking" |
| Music Lab controls (tempo, meter, groove, count-in) are in a left panel while results appear on the right, forcing horizontal eye-jumps on wide screens | 🟢 Minor | Consider stacking controls above the timeline on all screen sizes to create a top-down reading flow |
| "Expansion Runway" section shows future features that don't exist yet — users may click and expect something to happen | 🟡 Moderate | Dim more aggressively or add a "Coming Soon" badge with a visually distinct treatment |
| Copy button on the output box is invisible until hover — zero discoverability on touch devices | 🟡 Moderate | Show the copy button persistently (at reduced opacity) once a result is present, rather than relying on hover |
| Key selector in Builder mode only appears in NNS→Chords mode — users may not notice the mode toggle first | 🟢 Minor | Show key selector in both modes but disabled/grayed out with a tooltip in Chords→NNS mode |

---

## Visual Hierarchy

**What draws the eye first:** The gradient title "Nashville Numbers" and the purple Convert button — this is correct. The primary call to action is clearly the conversion flow.

**Reading flow:** Header → input area → convert button → output. Well-structured for the core converter. However, the page then continues into Music Lab and Fretboard sections with no clear separation — the user's eye loses anchor after the output box.

**Emphasis:** The Music Lab section competes with the main converter for visual weight. The groove preset cards, transport buttons, and timeline all use the same accent purple, making everything feel equally important. A slightly muted treatment for secondary surfaces would establish a clearer "convert first, explore second" hierarchy.

---

## Consistency

| Element | Issue | Recommendation |
|---------|-------|----------------|
| Border radii | 5 distinct values in use: `6px`, `7px`, `8px`, `10px`, `12px`, `14px` | Consolidate to 3 tokens: `--radius-sm` (6–8px), `--radius-md` (10–12px), `--radius-lg` (14px) |
| Font sizing | Section labels vary between `0.62rem`, `0.64rem`, `0.68rem`, `0.72rem` — four nearly identical sizes | Collapse to 2 label sizes: a standard section label and a small caption |
| Muted text treatment | Some elements use `opacity: 0.5` / `0.55`, others rely on `--text-muted`, some combine both | Pick one method: either `--text-muted` color OR opacity, not both |
| Letter spacing | Labels use `0.03em`, `0.04em`, `0.05em`, `0.08em`, `0.1em`, `0.12em` — six distinct values | Reduce to 2–3 presets: `--ls-tight: 0.04em` and `--ls-wide: 0.1em` |

---

## Accessibility

### Color Contrast

| Pairing | Ratio | WCAG AA (4.5:1) | Notes |
|---------|-------|-----------------|-------|
| `--text` (#e8e8ff) on `--surface` (#14142b) | ~14:1 | ✅ Pass | Primary body text |
| `--text-muted` (#8a8aaa) on `--surface2` (#1c1c38) | ~3.8:1 | ❌ Fail | Section labels, placeholders, footer |
| `--success` (#4ade80) on `--surface2` | ~8.5:1 | ✅ Pass | Output progression text |
| `--error` (#f87171) on `--surface2` | ~4.6:1 | ✅ Pass (barely) | Error output |

**Fix:** Bump `--text-muted` from `#8a8aaa` to approximately `#a0a0c0` to reach ~5:1 on dark surfaces.

### Touch Targets

- Note palette buttons: ~40×40px — slightly below the 44×44px recommended minimum
- Progression chip delete buttons (`.prog-chip-del`): ~16×16px — difficult to tap reliably on mobile
- **Fix:** Set `min-width: 44px; min-height: 44px` on note buttons; enlarge delete chip target area with padding

### Text Readability

- Monospace output at `1.05rem` / `line-height: 1.75` is comfortable ✅
- Several label sizes dip to `0.62–0.65rem` (~10px) — below the WCAG-recommended 12px minimum for body-adjacent text ❌

### Keyboard Navigation

- Good foundations: `aria-pressed`, `aria-selected`, `aria-live="polite"`, `role="tablist"` ✅
- Gap: Fretboard note dots are pointer-only (`pointerdown`/`pointerup`) — keyboard users cannot audition individual notes ❌
- **Fix:** Add `tabindex="0"` and `keydown` handler (Enter/Space) to `.fb-note-dot.playable` elements

---

## What Works Well

- **Design token system is solid.** 60+ CSS custom properties centralize theming. `clamp()` usage throughout creates genuinely fluid responsive behavior without brittle hard breakpoints.

- **Progressive disclosure is thoughtful.** The fretboard section starts hidden and only appears when the user interacts with a chord token. The Music Lab timeline is empty until "Build Arrangement" is clicked. This keeps the initial view focused.

- **The Builder mode is a clever innovation.** Offering both graphical chord construction (click note → click quality) and raw text input respects both beginners and power users. The progression track with animated chip insertion gives satisfying visual feedback.

- **Self-contained deployment is a genuine strength.** Zero external fetches, no CDN dependencies, no separate asset files. The entire UI ships as a Python string — installation friction is essentially zero.

- **Audio fallback strategy is well-communicated.** The status pill clearly shows "HQ Ready" vs "Web Tone Fallback," and install buttons appear inline rather than buried in settings. Users always know their audio path.

---

## Priority Recommendations

### P1 — Fix muted-text contrast ratios
**Why:** Single highest-impact accessibility change. Affects every section label, placeholder, footer, and caption.
**How:** Change `--text-muted: #8a8aaa` → `--text-muted: #a0a0c0`. No structural changes needed.

```css
/* Before */
--text-muted: #8a8aaa;

/* After */
--text-muted: #a0a0c0;
```

---

### P2 — Add visual separation between the converter and Music Lab
**Why:** Users lose orientation scrolling from the output box into the Music Lab without a clear boundary.
**How:** Elevate the "Music Lab" heading into a proper section divider with more top-margin and a horizontal rule, or make Music Lab a collapsible panel that starts closed.

```css
/* Stronger section break above Music Lab */
.music-lab-section {
  margin-top: clamp(2.5rem, 5vh, 4rem);
  padding-top: 2rem;
  border-top: 1px solid var(--border);
}
```

---

### P3 — Make copy button and interactive tokens discoverable on touch
**Why:** The copy button and clickable chord tokens rely entirely on hover — invisible to touch users, meaning the fretboard feature is effectively hidden.
**How (copy button):** Remove the `opacity: 0` default once `.has-result` is set; use `opacity: 0.45` instead and raise to `1` on hover/focus.
**How (tokens):** Add a brief pulse animation or persistent dashed underline on tokens in the output to signal interactivity on first render.

```css
/* Copy button — always visible when result present */
.output-box.has-result .btn-copy {
  opacity: 0.45;
  pointer-events: auto;
}
.output-box.has-result:hover .btn-copy,
.output-box.has-result .btn-copy:focus {
  opacity: 1;
}
```

---

## Summary Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| Visual Design | ⭐⭐⭐⭐½ | Strong identity, cohesive palette, good motion design |
| Usability | ⭐⭐⭐½ | Core flow is clear; builder mode UX has rough edges |
| Visual Hierarchy | ⭐⭐⭐½ | Converter hierarchy is good; Music Lab competes too strongly |
| Consistency | ⭐⭐⭐ | Token system exists but not fully enforced across components |
| Accessibility | ⭐⭐½ | Structural ARIA is solid; contrast and touch targets need work |
| Responsiveness | ⭐⭐⭐⭐ | `clamp()` usage is excellent; mobile fretboard slightly cramped |
