"""Reject publication unless Git advertises the previously verified bot head.

Git invokes this check before sending objects or updating the remote ref. A
subsequent concurrent write is also rejected by Git's server-side old-object
check. The expected SHA must come from the trusted preparation step, never from
the PR Action's refreshed remote-tracking ref.
"""

import itertools
import os
import re
import sys


MAX_INPUT_BYTES = 4096
ZERO_SHA = "0" * 40
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_COMPONENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")


def validate_updates(lines, branch, expected_sha):
    """Accept exactly one non-deleting update of the expected bot branch.

``lines`` may be a string or an iterable of text lines. Return ``None`` on
success; raise ``ValueError`` for malformed configuration, protocol input or a
remote head that differs from the preparation-time expectation.
"""
    if (not isinstance(branch, str) or not 1 <= len(branch) <= 200
            or ".." in branch or any(not _COMPONENT.fullmatch(part)
                                     or part.endswith((".", ".lock")) for part in branch.split("/"))
            or not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha)):
        raise ValueError("Invalid profile publication configuration")
    if isinstance(lines, str):
        if len(lines.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("Invalid profile publication input")
        entries = lines.splitlines(keepends=True)
    else:
        try:
            entries = list(itertools.islice(iter(lines), 2))
        except TypeError:
            raise ValueError("Invalid profile publication input") from None
    if len(entries) != 1 or not isinstance(entries[0], str):
        raise ValueError("Expected exactly one profile branch update")
    line = entries[0]
    if (len(line.encode("utf-8")) > MAX_INPUT_BYTES
            or any(ord(char) < 32 and char not in "\t\n" for char in line)
            or line.count("\n") > 1 or ("\n" in line and not line.endswith("\n"))):
        raise ValueError("Invalid profile publication input")
    fields = line.split()
    if len(fields) != 4:
        raise ValueError("Invalid profile publication input")
    local_ref, local_sha, remote_ref, remote_sha = fields
    allowed_ref = "refs/heads/" + branch
    if (local_ref != allowed_ref or remote_ref != allowed_ref
            or not _SHA.fullmatch(local_sha) or not _SHA.fullmatch(remote_sha)
            or local_sha == ZERO_SHA):
        raise ValueError("Only the configured profile branch may be updated")
    if remote_sha != expected_sha:
        raise ValueError("Profile branch changed after preparation")


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("Oversized hook input")
        validate_updates(raw.decode("utf-8"), os.environ.get("PROFILE_PROPOSAL_BRANCH"),
                         os.environ.get("PROFILE_EXPECTED_PR_SHA"))
    except (ValueError, TypeError, OSError):
        # Do not echo protocol input, environment contents or exception details.
        print("Profile publication refused: invalid update or remote branch changed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
