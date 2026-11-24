# Security Policy

## Supported Versions

Security fixes are made in the latest release only.

| Version | Supported |
| ------- | --------- |
| 2.4.x   | Yes       |
| < 2.4   | No        |

## Reporting a Vulnerability

Do not open a public issue for a vulnerability. Report it privately through GitHub:
<https://github.com/x96x64/HIStory/security/advisories/new>.

Include the version (`hist --version`), the steps to reproduce the problem and its effect. You can expect an
answer within a few days. A fix is released together with a security advisory that credits the reporter, unless the
reporter asks not to be named.

## Scope

`hist` makes no network connections and needs no credentials. It runs local tools (`ffmpeg`, `flac`, `exiftool`,
`osascript`, `SetFile`) and writes files in the catalog and library folders. Reports about unsafe handling of file
names, paths or tags are in scope.
