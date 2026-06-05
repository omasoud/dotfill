# Security Policy

## Supported Versions

Security fixes are supported for the latest released version of `dotfill` on
PyPI. Older releases may receive fixes at the maintainer's discretion, but users
should expect to upgrade to the latest release for security updates.

## Reporting a Vulnerability

Please do not report suspected security vulnerabilities in public GitHub issues.

Use GitHub private vulnerability reporting from the repository Security tab when
available. If private vulnerability reporting is unavailable, email the
maintainer listed in the package metadata.

When reporting, include:

- the affected `dotfill` version;
- the operating system and Python version;
- steps to reproduce the issue;
- the impact you believe the issue has;
- any relevant logs or screenshots with tokens, credentials, and `.env` values
  removed.

Please do not include real API tokens, credentials, private `.env` contents, or
other secrets in the report.

The maintainer will make a best effort to acknowledge reports within 7 days and
provide an initial assessment within 14 days. Confirmed vulnerabilities will be
handled privately until a fix, release, and advisory are ready when appropriate.

## Security-Sensitive Areas

Reports are especially useful for issues involving:

- API token leakage through logs, API responses, browser storage, or UI display;
- localhost session-token bypass, origin checks, or CORS behavior;
- unsafe `.env` writes, backups, path handling, or import-file handling;
- service-test request construction, authentication headers, TLS behavior, or
  redaction;
- package supply-chain or release-process weaknesses.

## Scope and Non-Goals

`dotfill` is a local-only developer tool that writes a user-selected `.env` file
and runs a localhost web UI. General support questions, expected behavior from a
user-provided configuration, or vulnerabilities in third-party services should
use the normal issue tracker or the affected upstream project unless they cause
`dotfill` to leak secrets, bypass local protections, or write outside the
intended target.

This project does not currently offer a paid vulnerability bounty program.
