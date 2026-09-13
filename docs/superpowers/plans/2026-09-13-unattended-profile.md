# Unattended Profile Implementation Plan

> Execute bounded publisher development and integration in parallel, then independently review and verify the final change.

**Goal:** Publish validated routine public-profile text updates without manual PR handling.

**Architecture:** Keep evidence collection, review limits and the existing state format. Replace the production PR publication steps with an exact-base, non-force README commit and post-publication checkpoint. Continue to force non-main runs into read-only mode.

**Tech Stack:** Python standard library, GitHub Git data API, GitHub Actions, existing DeepSeek interface.

- [x] Inspect current workflows/state and verify the 146-test baseline.
- [x] Add `scripts/profile_maintenance/publisher.py` and meaningful tests in `tests/test_publisher.py`: only README may change, exact checkout parent, strict response verification, race rejection, no checkpoint before confirmed publication and no blind write retry.
- [x] Integrate `publish` into `scripts/profile_maintenance/run.py` and its CLI tests. Direct mode must not require a bot branch push expectation, and no-change inputs must still skip paid review.
- [x] Replace draft PR steps in `.github/workflows/profile-maintenance.yml` with candidate tests and direct publication. Preserve read-only non-main dispatch and the existing single-run concurrency group.
- [x] Set explicit direct-publication policy and update `.github/PROFILE.md` to describe the final workflow, recovery behavior and maintenance boundaries.
- [x] Review remaining routine dependency-update handling; keep executable workflow changes separate from profile-text publication.
- [x] Run full unit tests, config validation, actionlint and diff checks; independently inspect the complete change.
- [x] Verify publication and race behavior against disposable GitHub refs using synthetic content before enabling main publication.
- [ ] Merge the reviewed implementation, run real evidence maintenance and verify an unchanged repeat produces zero model calls and zero writes.
- [ ] Finish any supported historical-record cleanup; report platform or connection limitations accurately rather than claim complete erasure.

## Verification before deployment

- 200 unit tests passed, including direct publication, concurrent ref changes, paid-review boundaries and conservative dependency merges.
- Configuration validation, actionlint 1.7.12 and whitespace checks passed.
- A real GitHub API smoke test on temporary refs published only README.md, checkpointed a no-change decision without another README commit, and rejected a last-moment concurrent branch update without advancing state.
- The smoke test left main unchanged and removed its temporary refs using exact SHA leases. It used synthetic content and did not call a model.
- Live dependency inspection found no open PRs. Actual future dependency merges remain gated by the tested evidence and successful exact-head checks.
