# Accessibility

Open PMS aims to meet [WCAG 2.2](https://www.w3.org/TR/WCAG22/) level AA, the standard UK public bodies must meet.

## What the automated tests check

`tests/test_accessibility.py` renders every page, including error states, and checks:
- the page language, a unique page title and exactly one main heading;
- a skip link to the main content, and a main landmark;
- a label for every field, and that hints and error messages are linked to their field;
- an error summary that is announced and links to each field with a problem;
- unique IDs, and header cells in every table;
- colour contrast of text, borders and the focus ring;
- buttons and links at least 44 pixels tall;
- the current page marked in the navigation.

## How the pages are built

- Plain HTML forms that work without JavaScript.
- RAG is always written in words ("Red: off track"), never shown by colour alone.
- Errors are listed at the top of the page and next to each field, in words.
- Layouts reflow to a single column on phones, with no sideways scrolling at 320 pixels wide.
- Motion is turned off for people who ask their system for reduced motion.

## Manual checks before each release

Machines can't check everything. Before each release, someone should work through this list on the main journeys: signing in, entering and submitting a value, approving and returning one, My week, My team, Exports and the admin screens.

| Check | How | WCAG |
|---|---|---|
| Keyboard only | Unplug the mouse. Every link, field and button can be reached with Tab, in a sensible order, and used with Enter or Space. Focus is always visible. Nothing traps focus. | 2.1.1, 2.4.3, 2.4.7, 2.4.11 |
| Screen reader | With NVDA (Windows) or VoiceOver (Mac, iPhone): headings make sense as a list, fields read their label, hint and error, status messages are announced after saving. | 1.3.1, 4.1.2, 4.1.3 |
| Zoom | At 200% and 400% browser zoom, nothing is cut off or overlaps, and there's no sideways scrolling at 400%. | 1.4.4, 1.4.10 |
| Text spacing | With a text-spacing bookmarklet, nothing is cut off. | 1.4.12 |
| Phone | On a real phone, every journey works in portrait and landscape. | 1.3.4, 2.5.8 |
| Plain language | Labels, hints and errors say what to do, in plain English. | 3.3.2 |
| Time limits | Sessions last 12 hours, so nobody loses work mid-form. | 2.2.1 |

Record the date, the browser and assistive technology used, and any problems found, in the release notes. Report accessibility problems as issues on GitHub.
