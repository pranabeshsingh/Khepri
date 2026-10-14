# Accessibility

Accessibility is a core priority for **Khepri**. We want everyone — including people with disabilities, people using assistive technology (such as screen readers or alternative input devices), and developers working in diverse terminal environments — to be able to use, configure, and contribute to Khepri.

This document outlines our accessibility commitments, our target standards, expectations for contributors, and instructions on how to report accessibility barriers.

---

## Priorities & Target Standards

- **Target Standard:** We work toward conforming with [WCAG 2.2 Level AA](https://www.w3.org/TR/WCAG22). This target guides our engineering and design decisions as an ongoing commitment.
- **Terminal & CLI Accessibility:**
  - Standard Unix stream separation: machine-readable generation outputs stream to `stdout`, while diagnostic logs, spinners, and warnings output to `stderr`.
  - ANSI colors respect color contrast guidelines and honor the `NO_COLOR` environment variable (per [no-color.org](https://no-color.org)) and `--no-color` flags.
  - Interactive REPL (`khepri chat`) provides clear text prompts without flickering or disruptive ANSI control sequences.
- **Web Companion UI Accessibility:**
  - **Keyboard Support:** Every interactive element (login forms, chat inputs, navigation tabs, note editors, and action buttons) is fully operable via keyboard alone.
  - **Focus Indicators:** Unambiguous, high-contrast visual focus rings are maintained across all interactive components without being disabled.
  - **No Keyboard Traps:** Focus moves logically through modals, popovers, and slide-over panels and returns smoothly upon dismissal.
  - **Screen Reader Support:** Semantic HTML5 (`<header>`, `<nav>`, `<main>`, `<section>`) and logical heading hierarchies (`<h1>` through `<h3>`) allow efficient navigation with VoiceOver, NVDA, Orca, and JAWS.
  - **Live Regions:** Dynamic asynchronous token streaming, agent status updates, and error alerts utilize `aria-live="polite"` regions so assistive technologies announce updates without interruption.
- **Telegram Interface:**
  - Interactive buttons and message cards provide plain text context alongside emojis.
  - High-information density responses (like daily briefings and calendar agendas) use structured Markdown lists with clear delimiters.

---

## Contributor Expectations

When contributing code, UI components, or documentation, please follow these guardrails to ensure we prevent accessibility regressions:

### 1. Interactive UI & Web Changes
- **Automated Audits:** Run automated accessibility audits (e.g., using [axe DevTools](https://www.deque.com/axe/devtools/) or Chrome Lighthouse) before submitting UI pull requests.
- **Keyboard-Only Pass:** Perform a manual keyboard-only test on any new or modified web component:
  - Tab order flows predictably from top to bottom, left to right.
  - Pressing `Tab`, `Shift+Tab`, `Enter`, `Space`, or arrow keys performs expected operations.
  - Focus is never lost or trapped in an inaccessible container.
- **Screen Reader Verification:** Spot-check that labels, form inputs, and buttons expose meaningful programmatic names rather than generic text or unlabeled icon SVGs.
- **Contrast & Resizing:** Ensure text elements maintain at least a 4.5:1 contrast ratio against their background, and interfaces reflow legibly when zoomed up to 200%.

### 2. Documentation & Visual Assets
- **Heading Hierarchy:** Do not skip heading levels (e.g., jump from `##` to `####`).
- **Alternative Text:** All architectural diagrams, flowcharts, and screenshots must include concise, descriptive `alt` text explaining the concepts illustrated.
- **Link Text:** Use clear, descriptive anchor text describing the destination (avoid vague phrases like "click here" or "read more").

---

## Reporting Accessibility Issues

If you encounter an accessibility barrier, keyboard navigation trap, or screen reader difficulty while using any part of Khepri:

1. **Open a GitHub Issue:**
   - File an issue on our [Issue Tracker](https://github.com/pranabeshsingh/Khepri/issues).
   - Apply the label `accessibility` (or note "Accessibility" in the title).
   - Describe the barrier encountered, the assistive technology or device used (e.g., screen reader name/version, browser, OS), and the expected behavior.
2. **Contact Directly:**
   - If you prefer to report an accessibility barrier privately, you can email the maintainer at **pranz29@live.com**.

We treat accessibility issues as critical usability bugs and prioritize remediation in upcoming releases.
