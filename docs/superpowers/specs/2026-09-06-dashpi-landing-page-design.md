# DashPi GitHub Pages 랜딩 페이지 설계

**작성일:** 2026-09-06

**상태:** 사용자 승인 디자인 반영

**배포 대상:** `https://jcmaker.github.io/DashPi/`

## 목표

DashPi를 처음 보는 학교 심사위원, 교수, 학생, 졸업전시 관람객, 개발자가 같은 페이지에서 각자의 깊이로 이해할 수 있게 한다.

방문자는 다음 순서로 정보를 얻는다.

1. 10초 안에 문제와 제품을 이해한다.
2. 실제 화면과 사고 처리 흐름을 확인한다.
3. 오프라인 동작, 증거 보존, 두 가지 전송 방식을 이해한다.
4. 구현 완료 범위와 하드웨어 검증 필요 범위를 구분한다.
5. GitHub 저장소에서 소스와 기술 문서를 확인한다.

## 범위

### 포함

- 한국어와 영어를 전환할 수 있는 단일 정적 페이지
- 한국어 모드에서 한국어 중심 문장과 핵심 영문 문구 병기
- 실제 DashPi 화면 3장과 저장소에 이미 있는 아이콘 사용
- 모바일, 태블릿, 데스크톱 대응
- GitHub Actions를 통한 GitHub Pages 배포
- 검색 및 공유를 위한 기본 메타데이터
- 키보드 탐색, 명확한 포커스, 모션 감소 설정 등 기본 접근성

### 제외

- 별도 CMS, 분석 도구, 쿠키 배너, 문의 폼
- FastAPI 또는 Ollama를 호출하는 온라인 데모
- 프로젝트 본체의 로컬 UI/PWA 변경
- 새로운 프런트엔드 프레임워크나 런타임 의존성
- 아직 완료되지 않은 Raspberry Pi 하드웨어를 완성품처럼 표현하는 문구

## 저장소 배치와 배포

랜딩 페이지는 제품 런타임인 `src/dashpi/web/`과 분리하여 저장소 루트의 `landing/`에 둔다.

```text
DashPi/
├── landing/
│   ├── index.html
│   ├── tokens.css
│   ├── styles.css
│   ├── script.js
│   ├── assets/
│   │   ├── icon.svg
│   │   ├── dashpi-incidents.jpg
│   │   ├── dashpi-optical-sender.jpg
│   │   └── dashpi-optical-receiver.jpg
│   └── THIRD_PARTY_NOTICES.md
└── .github/workflows/pages.yml
```

GitHub Actions는 `landing/`을 Pages artifact로 올리고 기본 브랜치의 성공한 배포만 공개한다. 페이지는 빌드 과정 없이 그대로 배포되는 HTML, CSS, JavaScript로 구성한다.

## 디자인 시스템

### 기준

디자인 기준은 Hallmark의 [Grid 01](https://www.usehallmark.com/examples/grid-01/)과 공개 저장소 [Nutlope/hallmark](https://github.com/Nutlope/hallmark)이다. 해당 구현은 MIT License이므로 실질적으로 재사용한 CSS와 디자인 소스에 저작권 및 라이선스 고지를 포함한다.

DashPi는 Grid 01의 다음 디자인 요소를 그대로 사용한다.

- 화면 전체에 노출되는 12열 헤어라인 그리드
- `Archivo` 400/500/600/700/800 단일 라틴 글꼴 체계
- 매우 굵고 촘촘한 디스플레이 타이포
- 작은 대문자 라벨과 넓은 자간
- 차가운 백지, 먹색, 신호 적색으로 제한한 팔레트
- 1px 규칙선, 각진 셀, 그림자와 카드가 없는 평면 구조
- 한 개의 강조색 전체 폭 플레이트
- 한 개의 느린 텍스트 티커
- 잘린 대형 숫자, 사각 마침표, quarter-disc, 계단형 막대 등 기하학 표식
- 행 hover 시 배경 전환, 8px 이동, 90도 회전처럼 짧고 격자에 맞는 반응

Grid 01의 행사 내용, 로고, 고유 명칭, 문장, 도형 배치는 사용하지 않는다. 동일 디자인 언어 위에 DashPi의 정보 구조와 QR/해시/사고 처리 모티프를 배치한다.

### 토큰

원본 Grid 01의 핵심 토큰을 유지한다.

```css
--color-paper: oklch(99% 0.003 255);
--color-paper-2: oklch(97.2% 0.003 255);
--color-paper-3: oklch(94.5% 0.004 255);
--color-ink: oklch(16% 0.010 255);
--color-muted: oklch(43% 0.012 255);
--color-rule: oklch(88% 0.006 255);
--color-accent: oklch(55% 0.21 28);
--font-display: "Archivo", "Helvetica Neue", Arial, sans-serif;
--font-body: "Archivo", "Helvetica Neue", Arial, sans-serif;
--tracking-display: -0.045em;
--tracking-label: 0.09em;
```

Archivo에는 한글 글리프가 없으므로 한국어는 `Noto Sans KR` 400–800을 같은 위치의 대체 글꼴로 사용한다. 라틴 문자는 두 언어 모드 모두 Archivo로 렌더링한다. 이 예외는 한글을 깨뜨리지 않으면서 원본의 무게와 비율을 가장 가깝게 유지하기 위한 것이다.

### 구조

**Macrostructure:** Poster Index 기반의 전시형 스토리텔링

**Theme:** Grid

**Navigation:** 얇은 상단 바에 wordmark, 섹션 링크, 언어 전환

**Footer:** 한 줄짜리 spare folio와 GitHub/문서/라이선스 링크

Hero는 왼쪽의 대형 `dashpi` wordmark와 두 줄짜리 설명, 오른쪽의 QR finder pattern을 재해석한 기하학 구성으로 나뉜다. 페이지 아래로 내려갈수록 numbered index, 적색 plate, 실제 화면 figure, 기술 spec table 순으로 정보가 깊어진다.

## 페이지 구성

### 1. 상단 바

- 왼쪽: `dashpi` wordmark와 적색 사각 마침표
- 오른쪽: `작동 방식`, `실제 화면`, `검증`, `GitHub`, `한국어 / EN`
- 모바일: 핵심 wordmark와 언어 전환, 메뉴 버튼만 유지

### 2. Hero

한국어 기본 문구:

> **dashpi.**
>
> 인터넷 없이 사고 영상을 보존하고, 로컬 AI로 분석하는 스마트 대시캠
>
> Understand and preserve an accident without depending on the cloud.

오른쪽에는 Grid 01의 기하학 구성 밀도와 크기를 따르되, quarter-disc 대신 QR finder pattern, frame block, 검증 표시를 조합한 순수 CSS 그래픽을 사용한다. Hero 안에는 CTA 버튼을 넣지 않는다.

### 3. 핵심 용어 티커

`OFFLINE-FIRST · EVIDENCE-FIRST · LOCAL AI · SHA-256 VERIFIED · LOCAL WI-FI · OPTICAL QR · RASPBERRY PI`

티커는 한 번만 사용하며 hover, focus, 모션 감소 설정에서 정지한다.

### 4. 사고 처리 numbered index

다음 네 단계를 전체 폭 행으로 보여준다.

1. 사고 전후 영상 수집 — 기본 30초 전, 15초 후
2. 원자적 저장과 SHA-256 검증
3. 12개 프레임 기반 로컬 Ollama 분석
4. Local Wi-Fi 또는 Optical QR 전송

각 행은 짧은 이름, 사실 기반 메타데이터, 기하학 표식으로 구성한다. 행을 누르면 같은 페이지의 상세 섹션으로 이동한다.

### 5. 단일 적색 plate

페이지에서 유일한 전체 적색 면으로 다음 메시지를 전달한다.

> **AI가 실패해도, 증거는 남습니다.**
>
> Evidence survives even when analysis fails.

배경 그리드는 낮은 불투명도로 plate 위에서도 계속 보인다.

### 6. 실제 동작 화면

저장소의 실제 캡처 3장을 figure cell로 표시한다.

- 사고 영상과 로컬 AI 리포트
- Animated QR 송신
- Offline Receiver PWA

이미지는 가짜 브라우저 프레임, 둥근 모서리, 그림자를 사용하지 않는다. 각 캡처에는 짧은 설명과 `실제 애플리케이션 캡처` 표기를 붙인다.

### 7. 두 가지 전송 방식

Grid 01의 spec table 형식을 사용하여 Local Wi-Fi와 Optical QR을 비교한다.

- 적합한 데이터
- 연결 방식
- 전송 방식
- 손실 대응
- 완료 검증
- 기밀성 한계

Optical QR이 암호화되지 않았고 일반 카메라 앱만으로 복원되지 않는다는 제한을 숨기지 않는다.

### 8. 구현과 검증

완료된 소프트웨어 검증과 남은 하드웨어 수락 시험을 시각적으로 분리한다.

- 완료: incident pipeline, 로컬 분석, atomic storage, ranged video, optical protocol, PWA, 자동 테스트
- 필요: Picamera2 장시간 녹화, 물리 trigger, hotspot, 화면/카메라 보정, 발열/전력, 전원 차단 복구

검증 수치는 저장소에서 확인 가능한 사실만 사용한다. 구현 당시 테스트 결과가 현재 값과 다르면 오래된 숫자를 노출하지 않고 검증 항목만 표기한다.

### 9. GitHub CTA와 footer

마지막 CTA는 `GitHub에서 DashPi 보기 ↗` 하나만 강조한다. 보조 링크로 README, PRD, TRD를 둔다.

저장소에 프로젝트 라이선스가 추가되기 전에는 페이지에서 DashPi를 법적인 의미의 `오픈소스`라고 단정하지 않는다. 대신 `GitHub에서 소스 보기`라고 표현한다. Hallmark MIT 고지는 `THIRD_PARTY_NOTICES.md`에 포함한다.

## 언어 전환

- 초기 언어는 한국어다.
- 전환 버튼은 `한국어`와 `EN`을 명시하고 현재 언어를 `aria-pressed`와 `<html lang>`으로 반영한다.
- 한국어 모드의 Hero, plate, 핵심 section head에는 짧은 영문 문구를 함께 노출한다.
- 영어 모드는 모든 본문, 캡션, 탐색, 접근성 레이블을 영어로 바꾼다.
- 선택 언어는 `localStorage`에 저장하되 저장소 접근 실패 시 현재 세션에서만 동작한다.
- 두 언어의 콘텐츠 키는 동일하게 유지하고 누락된 번역이 있으면 기본 한국어로 안전하게 대체한다.

## 접근성과 반응형

- 의미에 맞는 `header`, `nav`, `main`, `section`, `figure`, `table`, `footer` 사용
- 모든 기능을 키보드로 사용할 수 있게 하고 적색 포커스 링을 제공
- 본문과 라벨 대비를 WCAG AA 이상으로 유지
- 장식 도형은 `aria-hidden`, 의미 있는 시각 자료에는 대체 텍스트 제공
- `prefers-reduced-motion: reduce`에서 티커와 변형 애니메이션 제거
- 320px, 375px, 414px, 768px, 1024px 이상에서 수평 스크롤 없이 검증
- 모바일에서 12열은 유지하되 콘텐츠는 한 열로 재배치하고, 클릭 영역은 최소 44px 확보
- 클릭 가능한 문구는 모바일에서도 두 줄로 끊기지 않게 처리

## 오류와 제한 처리

- Google Fonts를 불러오지 못하면 시스템 sans-serif로 자연스럽게 대체한다.
- JavaScript가 꺼져도 기본 한국어 콘텐츠와 모든 핵심 링크는 보인다.
- 이미지 로딩 실패가 본문 이해를 막지 않도록 캡션과 대체 텍스트를 유지한다.
- GitHub Pages의 하위 경로 배포를 고려해 모든 내부 asset과 anchor는 상대 경로를 사용한다.
- 외부 API 요청, 사용자 데이터 입력, 쿠키는 사용하지 않는다.

## 검증

프레임워크를 추가하지 않고 다음 최소 검증만 남긴다.

1. HTML의 모든 내부 링크와 asset 경로가 존재하는지 확인한다.
2. 한국어와 영어 번역 키가 일치하는지 확인한다.
3. GitHub Pages artifact에 `index.html`, CSS, JavaScript, 이미지, MIT 고지가 모두 포함되는지 확인한다.
4. 브라우저에서 언어 전환, anchor 이동, 티커 정지, 키보드 포커스를 확인한다.
5. 320/375/414/768px와 데스크톱에서 수평 스크롤과 텍스트 겹침이 없는지 확인한다.
6. `prefers-reduced-motion`에서 자동 이동이 멈추는지 확인한다.

## 성공 조건

- 처음 보는 방문자가 Hero와 첫 index만 보고도 DashPi의 목적을 설명할 수 있다.
- 심사자가 실제 구현과 남은 하드웨어 작업을 혼동하지 않는다.
- 한국어와 영어 사이를 새로고침 없이 전환할 수 있다.
- 페이지가 GitHub Pages에서 저장소 하위 경로 문제 없이 열린다.
- 모바일과 키보드 환경에서 핵심 콘텐츠와 GitHub 링크를 사용할 수 있다.
- 화면에 표시되는 모든 기술 주장과 수치는 저장소 문서 또는 테스트로 근거를 확인할 수 있다.

## 의도적으로 생략한 것

React, Astro, Tailwind, 번역 라이브러리, 애니메이션 라이브러리, analytics는 이 한 페이지에 필요하지 않으므로 추가하지 않는다. 콘텐츠가 여러 페이지로 늘어나거나 비개발자가 자주 수정해야 할 때만 정적 사이트 생성기나 CMS를 검토한다.
