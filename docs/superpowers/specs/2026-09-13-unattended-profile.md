# Unattended profile maintenance

The owner authorizes routine updates within the existing public evidence and editorial boundaries to publish without a manual PR merge. This supersedes the earlier manual-publication policy. New projects, images, private material and protected professional facts remain outside automated editing.

Use the existing daily collector and bounded DeepSeek review. Unchanged successful evidence makes no model calls or writes. A candidate is validated and tested in the same trusted workflow; no automation-created PR or approval-dependent downstream CI is needed.

Publish a new single-parent commit containing only README.md. Its parent must be the exact checked-out main commit. Build the candidate through Git Blob/Tree/Commit APIs, verify the immutable commit and changed-file list, then advance main with a non-force Git ref update. Concurrent main changes defer publication; the workflow must not overwrite or weaken branch protections. Save the successful review checkpoint after publication. If checkpoint persistence fails after a successful commit, the next scheduled run can review the current README again; do not blindly retry a possibly completed write or roll back human work.

Maintain backward compatibility with the existing state schema and retain the old PR guards for any legacy state. An unknown or still-pending legacy PR must never be silently adopted or overwritten. Current deployment has no pending maintenance PR.

The implementation does not promise uninterrupted third-party services or erase platform-owned historical Git/PR data. Keep those limitations separate from the automation's completion status. Do not include retired project names or descriptions in new public maintenance records.
