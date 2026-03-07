## 2026-03-05 - Focus Management and ARIA States
**Learning:** Implementing `aria-pressed` for custom toggle buttons and programmatically managing focus back to the primary input after clear operations significantly enhances screen reader usability and keyboard flow.
**Action:** Ensure custom toggles dynamically sync their `aria-pressed` state with their visual `active` state, and always consider where the user's focus should land after disruptive or reset actions.

## 2025-03-07 - Keyboard Accessibility for Interactive Tokens
**Learning:** Interactive tokens that use `onclick` to update state must also include `role="button"`, `tabindex="0"`, and an `onkeydown` handler for "Enter" and "Space" keys to be accessible to keyboard users.
**Action:** Always verify that elements acting as buttons have proper keyboard event listeners and ARIA roles.
