# Profile Visual Preview Implementation Plan

> Use subagent-driven-development for the independent SVG artwork and disposable screenshot environment; integrate and review in this task.

**Goal:** Produce a reviewable personal-profile preview with a quiet SVG banner and one authentic sqlseed workbench screenshot, preserving the approved professional evidence.

**Architecture:** Keep the headline, capability summary and all project descriptions as Markdown. Add a two-theme local SVG illustration and a PNG captured from the real public candidate app with synthetic data. Visuals remain outside all AI-editable markers. Detailed architecture stays in the project repository.

**Tech Stack:** GitHub Markdown, SVG, PNG, existing Python maintenance checks.

## Accepted scope

- Change the heading from SunBo · sunbos to SunBo; add Python to the existing capability subtitle.
- Retain the visitor badge immediately below the name, with the same page_id.
- Preserve every existing project, technical detail, anonymized case, Star relationship, link and statistics image.
- Add assets/profile/banner-light.svg and banner-dark.svg: same restrained composition, compact dimensions, accessible title/description, no scripts or external resources.
- Add assets/profile/sqlseed-workbench.png only from an actual local candidate checkout, with synthetic demonstration data and a clear candidate-version caption. Do not fabricate model output or UI.
- Add assets/profile/README.md to document provenance, screenshot commit and update boundaries.
- Place all new visuals and captions outside profile-ai blocks; do not change the AI policy or invoke a paid model for layout work.
- Deliver through a new PR; publishing to main is not part of this preview request.

## Tasks and verification

- [x] Create an isolated branch from current main; verify the existing 146 tests pass.
- [x] Create and inspect both SVG themes, checking XML structure and absence of external resources.
- [x] Start a disposable sqlseed workbench from a public candidate commit, using synthetic SQLite data and isolated workspace/settings paths. Capture one authentic view of field rules or previews.
- [x] Integrate the images into README.md and write asset provenance. Keep the 6 editable blocks byte-for-byte identical to main.
- [x] Render GitHub Markdown and inspect desktop/light/dark/mobile presentation. Check local image references, all existing content, the Star table and protected image placement.
- [x] Run the existing test suite and git diff --check; no new tests are needed for this reversible visual-only change.

## Validation results

- 146 existing tests passed; independent text/SVG review found no blocking issues.
- The six AI-editable sections and two approved anonymized cases are byte-for-byte identical to the base README. Existing links and statistics images remain present.
- Real offline preview returned HTTP 200, `ok=true`, `preview_complete=true` and no issues; the screenshot shows five synthetic order samples after completion. No database fill or model call was performed.
- GitHub-rendered Markdown was viewed in a fresh local test browser using GitHub styles: desktop at 1120 px in both themes and mobile at 390 px. All images loaded, the correct banner theme was selected, and no page-wide horizontal overflow occurred. These captures are local layout previews, not screenshots of the published profile.
- The PNG is 2040 × 1500 with no embedded text/EXIF metadata. The two SVG files are valid XML without scripts or external resources.

Delivery: publish the verified branch as a draft PR for visual review. Merging this preview requires a subsequent user decision.
