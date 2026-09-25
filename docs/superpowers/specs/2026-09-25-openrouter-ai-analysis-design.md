# OpenRouter 기반 사고 분석 설계

**날짜:** 2026-09-25
**상태:** 설계 승인 대기
**대체 범위:** [OpenAI API 분석 핸드오프](2026-09-24-openai-api-analysis-handoff.md)의 결정을 구체화하며, [네이티브 앱 설계](2026-09-24-native-pi-app-design.md)의 로컬 Ollama 분석 부분을 대체한다. 녹화·사고 수집·증거 보존·리포트 HTML·광학 QR·객체 추적은 바꾸지 않는다.

## 1. 목적과 성공 기준

Raspberry Pi 5(4GB)의 RAM을 녹화·ffmpeg·객체 추적에 남기기 위해 AI 분석을 외부 API로 옮긴다. 분석을 맡는 곳을 바꾸는 작업이며 새 사용자 기능은 추가하지 않는다.

성공 기준:

1. 인터넷이 있을 때 Pi에서 **사고 분석 → 분석 완료 → QR 전송**이 끝까지 동작한다.
2. 인터넷이 없을 때도 사고 영상은 지금처럼 보존되고, 사고는 **분석 대기** 상태가 되며, 연결되면 사람의 조작 없이 분석이 완료된다.
3. 버그나 오조작이 있어도 비용은 결제 쪽 한도와 앱의 하루 한도를 넘지 않는다.
4. 팀원은 API 비용 없이 전체 흐름을 테스트할 수 있고, 자동 테스트는 외부 API를 호출하지 않는다.
5. 평가 하네스로 모델·프롬프트 조합의 품질·지연·비용을 같은 사례에서 비교할 수 있다.

## 2. 결정 사항

| 항목 | 결정 |
| --- | --- |
| 제공 경로 | OpenRouter, OpenAI 호환 Chat Completions (`POST {base_url}/chat/completions`) |
| HTTP | 표준 라이브러리 `urllib`. 새 의존성 없음 |
| 기본 모델 | `openai/gpt-6-sol` (설정에서 변경 가능) |
| 입력 | 영상 전체가 아니라 추출 프레임(JPEG). 긴 변 1024px로 축소 |
| 출력 | JSON Schema 강제 (`response_format` = `json_schema`, `strict: true`) |
| 데이터 경로 | `provider: {"data_collection": "deny"}`로 데이터를 수집할 수 있는 제공사 제외 |
| 네트워크 없음 | 새 상태 `awaiting_analysis`(분석 대기) + 앱 내 자동 재시도 |
| 로컬 AI | Ollama 코드·설정·CLI 옵션 제거 |
| 공개 문서 | 랜딩·README에 제공사 이름을 쓰지 않는다 |

## 3. AI 역할

한 번의 호출이 모든 것을 하던 구조를 채점 가능한 세 역할로 나눈다. 이미지가 필요한 역할과 텍스트만 쓰는 역할을 분리해 이미지 전송을 최소화한다.

| 역할 | 호출 | 입력 | 출력(스키마) |
| --- | --- | --- | --- |
| A. 사고 시점 탐지 | 비전 | 클립 전체에서 균등 추출한 12장 + 각 프레임의 클립 기준 시각 | `incident_timestamp`(초), `confidence`(0–1), `reason`(짧은 근거) |
| B. 장면 관찰 | 비전 | A 시각 전후 ±3초(클립 경계 안)에서 균등 추출한 12장 + 시각 | `observations`: `[{timestamp, description}]` — 사실만, 판단 없음 |
| C. 리포트 요약 | 텍스트 | B의 관찰 목록 | `summary`(한국어), `limitations`(목록) |

- 외부 영상 분석처럼 사람이 사고 시점을 지정한 경우(`incident_offset_override`)에는 A를 건너뛰고 지정 시각을 쓴다.
- 세 결과를 합쳐 기존 `validate_report()` 입력 형식(`incident_timestamp`, `summary`, `observations`, `limitations`)을 만든다. `confidence`와 `reason`은 리포트 JSON의 `analysis` 항목에 보존하되 기존 검증 스키마는 바꾸지 않는다.
- 모든 프롬프트는 "화면에 보이는 사실만, 법적 과실을 판단하지 말 것"을 명시한다. 출력 언어는 한국어로 고정한다.
- 호출별 모델은 기본적으로 같은 설정 모델을 쓰고, 하네스와 환경 변수로 역할별 모델을 바꿀 수 있다.

### Grok 후보

OpenRouter의 Grok 중 블랙박스 영상 전용 모델은 없다. 모두 이미지 입력과 structured outputs를 지원하는 범용 모델이므로 역할별 후보로 하네스에서 비교한다.

| 모델 | 가격(입력/출력, 1M 토큰) | 비교 대상 역할 | 이유 |
| --- | --- | --- | --- |
| `x-ai/grok-4.7` | $1.6 / $4.8 | A, B | 현재 플래그십. 자기 검증에 강함 |
| `x-ai/grok-4.20` | $1.25 / $2.5 | C (및 A) | "가장 낮은 환각률과 엄격한 지시 준수"를 내세움 → 사실만 요약해야 하는 C에 적합 |
| `x-ai/grok-4.3` | $1.25 / $2.5 | C 대안 | 사실 정확성·지시 준수 지향의 추론 모델 |

`grok-build-0.1`(코딩 전용), `grok-4.20-multi-agent`(연구용 병렬 에이전트, 느리고 비쌈)은 제외한다. 기본값은 하네스 결과로 확정한다.

## 4. 구성 요소

### 4.1 `src/dashpi/ai_client.py` — OpenAI 호환 클라이언트

- `ChatClient(base_url, api_key, timeout=60)` — `complete(model, messages, schema, max_tokens) -> dict`.
- 요청 본문: `model`, `messages`, `response_format`(json_schema, strict), `max_tokens`, `reasoning: {"effort": …}`, `provider: {"data_collection": "deny"}`.
- 추론 모델은 추론 토큰이 `max_tokens`를 먼저 소모해 JSON이 잘릴 수 있다. 역할별 `reasoning.effort`를 두고 기본값은 `low`로 한다. 응답이 `finish_reason: "length"`로 끝나면 `AnalysisError`("응답이 잘림")로 처리하고, 하네스가 역할별 적정 `max_tokens`·`effort`를 측정한다.
- 응답에서 `choices[0].message.content`를 JSON으로 파싱한다. `message.refusal`이 있으면 거부로 처리한다. `usage`(토큰 수)를 결과와 함께 반환해 하네스가 비용을 계산한다.
- 기존 `OllamaClient`처럼 리다이렉트를 따르지 않는다. 프록시 환경 변수는 존중한다(차량 핫스팟·학교 네트워크 대비).
- 오류 분류:
  - `RetryableAnalysisError`: 연결 실패·DNS 실패·시간 초과, HTTP 408/429/5xx, API 키 없음.
  - `AnalysisError`: HTTP 400/401/402/403/404, 거부, JSON 파싱 실패, 응답 형식 이상.
  - 402(크레딧 부족)는 재시도로 해결되지 않으므로 `AnalysisError`로 두고 사유에 "크레딧 부족"을 남긴다.

### 4.2 `src/dashpi/analysis.py` — 역할과 분석기

- 역할 A·B·C의 프롬프트와 JSON Schema를 한 파일에 둔다.
- `Analyzer(client, models, frame_sampler)`는 `analyze(clip_path, work_dir, incident_offset_override=None) -> dict`로 A→B→C를 실행하고 `validate_report()` 입력 형식을 반환한다.
- `FakeAnalyzer`: 네트워크 없이 클립 길이에 맞는 결정적 리포트를 반환한다. 설정 모델이 `fake`이면 사용한다.
- `load_ai_config(path=~/.config/dashpi/ai.env)`: `KEY=VALUE` 형식을 읽는다. 키: `DASHPI_AI_API_KEY`(필수), `DASHPI_AI_BASE_URL`(기본 `https://openrouter.ai/api/v1`), 선택 `DASHPI_AI_MODEL_LOCATE`/`_OBSERVE`/`_REPORT`. 같은 이름의 환경 변수가 파일보다 우선한다. 파일 권한이 그룹·기타 사용자에게 열려 있으면 경고를 로그에 남긴다.

### 4.3 파이프라인 변경 (`pipeline.py`, `media.py`)

- `analyze` 인자의 형태를 `analyze(frames)`에서 `analyze(clip_path, work_dir, incident_offset_override)`로 바꾼다. 프레임 추출은 분석기가 맡는다.
- `sample_frames(clip, output_dir, count, start=0.0, end=None, max_edge=1024)`: 구간과 축소를 지원한다(`ffmpeg -vf scale`).
- `generate_report()`에서 `RetryableAnalysisError`는 `AWAITING_ANALYSIS`로 전이하고 `failure_reason`에 사유를, 새 필드 `analysis_attempts`, `next_analysis_at`(ISO 시각)에 재시도 정보를 저장한다. 다른 예외는 지금처럼 `ANALYSIS_FAILED`.
- `report_model` 기록은 실제 사용 모델(역할별이 다르면 `locate/observe/report` 모델 목록)로 한다.
- `Settings.ollama_model` → `Settings.ai_model`, `VideoSettings.ollama_model` → `VideoSettings.ai_model`(기본 `openai/gpt-6-sol`). `load_settings()`는 기존 `ollama_model` 키를 무시하고 기본값을 쓴다.

### 4.4 상태 (`models.py`)

- `IncidentState.AWAITING_ANALYSIS = "awaiting_analysis"` 추가. 전이: `analyzing → awaiting_analysis → analyzing → ready | analysis_failed`.
- `IncidentMetadata`에 `analysis_attempts: int = 0`, `next_analysis_at: str | None = None` 추가. 기존 메타데이터 파일은 기본값으로 읽힌다.
- 표시 문구: `awaiting_analysis` → "분석 대기".

### 4.5 재시도 (`src/dashpi/analysis_retry.py`)

- `AnalysisRetrier(store, pipeline_factory, worker, analyzer_factory, clock)` — `tick(now)`가 대기 사고 중 `next_analysis_at`이 지난 것을 하나씩 `worker`에 제출해 `pipeline.regenerate_report()`(클립 해시 검증 후 재분석)를 실행한다. 한 번에 하나만 실행한다.
- 재시도 간격: 1분 → 2분 → 5분 → 10분 → 이후 30분 고정.
- 앱 시작 시 `awaiting_analysis`와, 분석 중 앱이 종료돼 남은 `analyzing` 사고를 즉시 대상에 넣는다.
- Pi 앱은 `QTimer`로 60초마다 `tick()`을 호출한다. 녹화 중 사고 수집이 진행 중이면 기존 `worker.wait_for_capacity()` 규칙을 따른다.
- 웹 서버(`server.py`)는 수동 재생성만 제공하며 자동 재시도는 하지 않는다.

### 4.6 비용 안전장치 (`src/dashpi/ai_budget.py`)

- 하루 분석 한도(기본 20건, 환경 변수 `DASHPI_AI_DAILY_LIMIT`)를 `<data_root>/ai-usage.json`(`{"date": "YYYY-MM-DD", "count": n}`)에 원자적으로 기록한다. 사고 1건(A·B·C 묶음)을 1건으로 센다.
- 한도에 도달하면 `RetryableAnalysisError("오늘 분석 한도에 도달했습니다")`를 내고, 다음 시도 시각은 다음 날 00:05(기기 현지 시각)로 둔다.
- 호출별 `max_tokens`: A 300, B 1500, C 1200.
- 프레임은 역할당 12장, 긴 변 1024px로 고정한다.
- 결제 쪽 한도는 운영 절차(§8)로 둔다. 앱 한도는 버그로 인한 폭주를 막는 두 번째 방어선이다.

### 4.7 Pi 앱 (`desktop.py`)

- 설정 화면의 "로컬 AI 모델" → "AI 모델"(자유 입력, `fake` 허용). 아래에 캡션 "API 키: 설정됨 / 없음"(키 값은 표시하지 않음).
- 녹화기록 목록과 상세에 "분석 대기" 상태와 사유(예: "인터넷 연결 없음 · 다음 시도 14:32")를 보인다.
- `OllamaClient` 사용 지점(녹화 세션, 외부 영상 분석)을 분석기 생성 함수 하나로 바꾼다.
- 상세 화면: `analysis_failed` 사고에도 **사고 분석** 버튼을 보여 재분석할 수 있게 한다(키·크레딧 문제를 고친 뒤 경로). 누르면 `awaiting_analysis`로 바꾸고 즉시 재시도 대상에 넣는다.
- 로그에 역할별 모델, 소요 시간, 토큰 수, 재시도 전이를 남긴다. API 키와 이미지 내용은 로그에 남기지 않는다.

### 4.8 CLI와 웹 서버

- `dashpi simulate`: `--ollama-model` → `--ai-model`(기본 `openai/gpt-6-sol`). `validate_model()` 호출 제거.
- `dashpi-server`: `--ollama-model` → `--ai-model`. 수동 재생성은 같은 분석기를 사용한다.
- `reports.py`에서 `OllamaClient`와 관련 헬퍼를 제거한다. `validate_report()`와 `render_report_html()`은 유지한다.

### 4.9 문서

- README: Ollama 설치·모델 준비 안내를 "AI 분석 API 키 설정(`~/.config/dashpi/ai.env`)"으로 바꾸고, 저장 구조에 `ai-usage.json`, 상태 다이어그램에 `awaiting_analysis`를 추가한다. 제공사 이름은 쓰지 않는다.
- `ai.env.example`을 저장소 루트에 두고 `.gitignore`에 `ai.env`, `eval/cases/*/clip.mp4`, `eval/results/`를 추가한다.
- `docs/AGENT_HANDOFF.md`의 분석 백엔드 설명을 이 문서로 연결한다.

## 5. 평가 하네스 (`dashpi eval`)

- 사례 폴더: `eval/cases/<case_id>/clip.mp4`(저장소에 올리지 않음, `.gitignore`) + `expected.json`(커밋).
- `expected.json`: `incident_timestamp`, `timestamp_tolerance`(기본 1.0초), `must_observe`(관찰에 있어야 할 사실 키워드 목록), `must_not_claim`(없는 사실·과실 표현 목록).
- 실행: `dashpi eval --cases eval/cases --model openai/gpt-6-sol --model x-ai/grok-4.7 [--locate-model …] [--observe-model …] [--report-model …] --out eval/results/<날짜>.jsonl`.
- 사례·모델 조합마다 역할별 출력, 소요 시간, 토큰 수, 추정 비용(OpenRouter `/models` 가격 기준, 실행 시 조회)을 JSONL로 저장하고 요약 표를 출력한다.
- 채점:
  - A: `|예측 − 정답| ≤ tolerance`면 통과, 오차(초) 기록.
  - B: `must_observe` 키워드 재현율, `must_not_claim` 위반 수.
  - C: `must_not_claim` 위반 수(과실·책임 표현 기본 포함), 관찰에 없는 고유 명사·숫자 등장 수.
- 실행 전 예상 최대 비용(사례 수 × 모델 수 × 호출당 상한)을 출력하고 `--yes` 없이는 확인을 받는다.
- 사례 확보는 구현 계획에서 정한다(Pi 촬영, 팀 확보 블랙박스 영상, 공개 영상 중 선택). 사례가 없어도 하네스 코드와 채점 테스트는 완성한다.

## 6. 오류 처리 요약

| 상황 | 상태 | 사용자 표시 |
| --- | --- | --- |
| 인터넷 없음·DNS·시간 초과 | 분석 대기 | "분석 대기 · 인터넷 연결 없음 · 다음 시도 HH:MM" |
| 429·5xx | 분석 대기 | "분석 대기 · 분석 서버 일시 오류 · 다음 시도 HH:MM" |
| API 키 없음 | 분석 대기 | "분석 대기 · API 키 없음" |
| 하루 한도 | 분석 대기 | "분석 대기 · 오늘 분석 한도 도달" |
| 401·403 | 분석 실패 | "분석 실패 · API 키 확인 필요. 원본 영상은 보존됩니다." |
| 402 | 분석 실패 | "분석 실패 · 크레딧 부족. 원본 영상은 보존됩니다." |
| 400·거부·형식 검증 실패 | 분석 실패 | "분석 실패 · …. 원본 영상은 보존됩니다." |

분석 실패 사고는 자동 재시도하지 않는다. 사람이 다시 분석하려면 외부 영상과 같은 **사고 분석** 버튼을 상세 화면에 제공한다(키를 고친 뒤 재분석하는 경로).

## 7. 테스트

- `ai_client`: 로컬 `http.server` 가짜 서버로 성공, 거부, 각 HTTP 코드, 연결 실패, 시간 초과의 분류를 검증한다. 요청 본문에 `response_format`, `provider.data_collection`, `max_tokens`가 들어가는지 검증한다.
- `analysis`: 가짜 클라이언트로 A→B→C 순서, B의 구간 계산(클립 경계 포함), override 시 A 생략, 결과가 `validate_report()`를 통과하는지.
- 파이프라인: `RetryableAnalysisError` → `awaiting_analysis`와 재시도 필드, 다른 오류 → `analysis_failed`, 원본 클립 보존.
- 재시도: 가짜 시계로 간격(1·2·5·10·30분), 앱 재시작 시 `analyzing` 복구, 한 번에 하나만 실행.
- 예산: 날짜 바뀜 초기화, 한도 도달 시 다음 날 시각.
- 설정: 기존 `ollama_model` 키가 있는 파일 읽기, `ai.env` 우선순위와 권한 경고.
- 하네스: 채점 함수와 비용 계산(가격표 고정 입력), 확인 없이 실행 거부.
- Pi UI: "분석 대기" 표시, 설정 화면 키 상태 캡션.
- 모든 자동 테스트는 외부 네트워크를 호출하지 않는다.

## 8. 운영 절차 (비용·키)

1. OpenRouter 계정에 선불 크레딧을 충전하고 **자동 충전을 끈다**.
2. 계정 설정에서 학습 가능 제공사로의 라우팅을 끈다(요청의 `data_collection: "deny"`와 이중 방어).
3. 용도별 API 키를 만들고 키마다 사용 한도를 건다: `dashpi-pi`($5), `dashpi-junhyeong`($5), 팀원별(`$2`).
4. 키는 각자 `~/.config/dashpi/ai.env`에 두고 `chmod 600`. 저장소에는 `ai.env.example`만 둔다.
5. 키 유출·오사용 시 해당 키만 비활성화한다.

## 9. Pi 배포와 수락 시험

1. `main`을 Pi의 `~/DashPi-native`로 `git pull`, 앱 재시작.
2. 준형이 Pi용 키를 `~/.config/dashpi/ai.env`에 넣는다(`chmod 600`).
3. 설정 화면에서 "API 키: 설정됨" 확인, AI 모델 기본값 확인.
4. 수락 시험:
   - 인터넷 연결 상태에서 주행 녹화 → 사고 분석 → 15초 후 종료 → **분석 완료** → 리포트 QR 전송.
   - Wi-Fi를 끈 상태에서 같은 흐름 → **분석 대기** 표시 → Wi-Fi 복구 → 사람 조작 없이 **분석 완료**.
   - 로그에서 역할별 소요 시간·토큰 수 확인, RAM 사용량이 Ollama 대비 증가하지 않음을 확인.
5. Pi의 Ollama 서비스는 수락 시험 통과 후 중지·비활성화한다(삭제는 별도 결정).

## 10. 범위 밖

- 조치 안내, 경찰·보험사 전달문(향후 역할 D·E 후보)
- 영상 전체 업로드, 스트리밍 응답
- 앱 내 API 키 입력 UI
- 웹 서버의 자동 재시도
- 랜딩·README에 제공사 명시
