# Post-incident guidance statement

## Goal

Reframe the red statement band around DashPi's user value: helping a shaken driver understand what to do after a crash and communicate the situation to police, insurers, or other responders.

## Content

- Replace the current AI-failure headline with: `사고 직후에는, 무엇을 해야 할지 판단하기 어렵습니다.`
- Add one supporting paragraph explaining that DashPi organizes the recorded situation and next steps so the driver can act and hand over the relevant facts without omissions.
- Provide equivalent English copy through the existing language toggle.
- Replace the unexplained decorative `45` with `NEXT` to reinforce the next-action and handoff theme.

## Boundaries

- Do not imply that DashPi determines fault, legal responsibility, or a definitive interpretation of the crash.
- Do not change the surrounding flow, evidence, transfer, verification, or footer sections.
- Reuse the existing statement-band markup, translation mechanism, and typography.

## Verification

- Add a landing-page regression test for the Korean and English statement copy and the `NEXT` backdrop.
- Run the landing tests, full Python suite, web tests, web build, and `git diff --check`.
