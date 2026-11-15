# Security Policy

## Supported versions

Security fixes are provided for the latest release only. Please upgrade to the newest release before reporting an issue.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub's Private Vulnerability Reporting:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue, the affected version, and how to reproduce it.

Expect an acknowledgement within a few business days, updates while the report is investigated, and credit in the release notes when a fix ships unless you ask to stay anonymous.

## Scope

This integration runs inside Home Assistant and sends commands to a USB Zigbee adapter through ZHA. Relevant reports include anything that lets an unprivileged Home Assistant user or a network peer send arbitrary frames to the adapter, crash Home Assistant or ZHA, or read data they should not. Include your Home Assistant version, the integration version and the ZBT-2 firmware version.
