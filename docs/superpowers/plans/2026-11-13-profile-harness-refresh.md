# Profile Harness Refresh Implementation Plan

> **For agentic workers:** Use inline execution for these small editorial changes; review the final diff independently.

**Goal:** Refresh the GitHub profile around AI application and Harness engineering with a shorter, clearer project-first layout.

**Architecture:** Keep GitHub-native Markdown and the existing original SVG illustration. Preserve all five managed `profile-ai` regions byte-for-byte, keep non-public experience anonymized, and leave generated statistics untouched.

**Tech Stack:** GitHub Flavored Markdown, inline SVG, existing Python validation.

## Tasks

- [x] Update `README.md` introduction and navigation; lead with sqlseed and the existing anonymized stability case, fold secondary details, and replace the dense capability table with concise links.
- [x] Update both `assets/profile/banner-*.svg` text layers and accessible descriptions without changing the illustration paths or theme colors.
- [x] Synchronize `assets/profile/README.md`, `.github/PROFILE.md`, and the existing anonymized-case policy test with the new title and order.
- [x] Run `python3 -m unittest discover -s tests -q`, `python3 -m scripts.profile_maintenance.run validate`, and `git diff --check`; compare managed regions with the baseline.
- [x] Render using GitHub's Markdown API and inspect wide/narrow previews and both banner themes in a browser.
- [x] Review the diff, then prepare the verified change for publication to the profile repository.

## Design decisions

- Preserve the blue/gold bracket-and-check illustration and its light/dark palettes.
- Use GitHub's native body typography; the banner keeps the existing system font stack and three-level type hierarchy.
- Keep one left-aligned column; shorten the route from introduction to representative work.
- Put framework names in project details. Do not claim RSI, autonomous learning, or unmeasured model effectiveness.
- Use only previously published anonymized case facts; do not add private repository names, URLs, deployment details, or measurements.

## Validation

- 200 existing tests passed; all five managed regions are unchanged.
- Both SVGs parse successfully and retain the original illustration paths.
- GitHub Markdown API rendering was inspected at desktop and 390 px widths, in light and dark themes; navigation and disclosure behavior were checked.
- Independent review found no blocking issues.
