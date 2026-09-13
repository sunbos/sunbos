# Profile Visual Preview Implementation Plan

**Goal:** Produce a reviewable personal-profile preview with a quiet SVG banner, preserving the approved Python and AI engineering experience.

**Approach:** Keep the headline, capability summary and project descriptions as Markdown. Add a two-theme local SVG illustration outside all AI-editable markers. Detailed architecture stays in the project repository.

**Tech Stack:** GitHub Markdown, SVG, existing Python maintenance checks.

## Accepted scope

- Change the heading from SunBo · sunbos to SunBo; add Python to the existing capability subtitle.
- Retain the visitor badge immediately below the name, with the same page_id.
- Add assets/profile/banner-light.svg and banner-dark.svg: same restrained composition, compact dimensions, accessible title/description, no scripts or external resources.
- Keep the sqlseed project descriptions, two approved anonymized cases, Dify SDK contribution, sunbo-skills, curated Stars and existing statistics images.
- Keep product screenshots and additional project showcases out of the profile until the owner confirms they are ready to display.
- Limit maintenance to four approved public sources and five editable blocks. Retain the remaining block contents byte-for-byte and keep the existing preservation constraints.
- Document asset provenance and the deferred showcase boundary. Do not invoke a paid model for this layout change.
- Deliver through the existing draft PR; publishing to main requires a subsequent owner decision.

## Verification

- Inspect both SVG themes, checking XML structure and absence of external resources.
- Verify the two approved anonymized cases, five remaining editable blocks, curated Star table and existing statistics links remain intact.
- Validate the updated four-source, sixteen-file, five-block maintenance configuration.
- Run the existing test suite and git diff --check. No new tests are needed for these reversible editorial/configuration changes.
- Render GitHub Markdown and inspect desktop/light/dark/mobile presentation, including banner selection and image references.
- Push the revision to the existing draft PR and verify its checks before showing the updated preview.
