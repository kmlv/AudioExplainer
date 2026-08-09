# Security policy

## Supported versions

AudioExplainer is currently an alpha project. Security fixes are applied to the
latest `0.1.x` release and the current default branch on a best-effort basis.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability or exposed
credential. Use
[GitHub private vulnerability reporting](https://github.com/kmlv/AudioExplainer/security/advisories/new)
for this repository.

Include the affected version, reproduction steps, potential impact, and any
suggested mitigation. You should receive an acknowledgment within seven days.

## Sensitive text and online speech

The Edge provider sends narration text to an online Microsoft service. Use the
local Piper or system provider for confidential material. The built-in safety
check reduces accidental disclosure but is not a substitute for reviewing input
before synthesis.
