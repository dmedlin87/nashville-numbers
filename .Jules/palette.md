## 2026-03-05 - Focus Management and ARIA States
**Learning:** Implementing `aria-pressed` for custom toggle buttons and programmatically managing focus back to the primary input after clear operations significantly enhances screen reader usability and keyboard flow.
**Action:** Ensure custom toggles dynamically sync their `aria-pressed` state with their visual `active` state, and always consider where the user's focus should land after disruptive or reset actions.

## 2026-03-05 - Keyboard Focus for Interactive Output Tokens
**Learning:** Output tokens generated dynamically (like chord or key spans) cannot be focused by a keyboard user unless they receive standard interactive attributes (`tabindex="0"`, `role="button"`). Similarly, `onclick` handlers do not implicitly capture keyboard events for non-button elements.
**Action:** When creating interactive UI elements from `span` or `div` tags, always provide `tabindex="0"`, a `role`, and an `onkeydown` handler supporting both "Enter" and " " (Space) keys to ensure screen readers and keyboard-only users can trigger the expected action.
