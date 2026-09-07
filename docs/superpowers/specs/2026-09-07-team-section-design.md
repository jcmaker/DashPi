# School and team section

## Goal

Add project provenance and contributor roles after verification, without interrupting the product story or exposing incomplete profile data.

## Content and placement

- Place the section between Verification and the GitHub source call-to-action.
- Show `경기과학기술대학교 · 디자인공학과 · 캡스톤디자인` above the heading `이 프로젝트를 만든 사람들`.
- Present six equal team entries: 조준형 — Software; 채현수 — Hardware · CAD; 우지혁 — CAD; 최재혁; 최준명; 신태영.
- Omit missing roles entirely until they are known. Do not render placeholders such as `확인 필요`.
- Provide equivalent English labels and roles through the existing language toggle.

## Presentation

- Reuse the landing page's 12-column editorial grid, typography, rules, spacing tokens, and i18n mechanism.
- Use a text-only three-column grid on wide screens and one column on small screens.
- Do not add portraits, biographies, social links, dependencies, or JavaScript behavior.

## Verification

- Extend the existing landing-page regression test to cover placement, all six names, known roles, translations, and the absence of placeholder copy.
- Run the focused landing test, full Python suite, web tests, web build, and `git diff --check`.
