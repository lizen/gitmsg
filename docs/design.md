# gitmsg — Nativ 로컬 LLM 기반 커밋 메시지 생성기 설계

- 작성일: 2026-09-14
- 상태: 승인됨

## 1. 목적

로컬에 로드한 LLM을 Nativ 앱의 REST API로 호출해서, IntelliJ IDEA로 작업하는
git 저장소의 커밋 대상 변경분을 검토하고 커밋 메시지 초안을 만든다.

사용자는 `~/work/` 아래 20여 개 저장소를 오가며 작업한다. 따라서 저장소마다
설정을 복제해야 하는 방식은 쓰지 않는다.

## 2. 확인된 환경

### Nativ

- `Nativ.app` 0.3.7, 번들 ID `io.github.blaizzy.nativ`
- OpenAI 호환 REST API. 기본 주소 `http://127.0.0.1:8080`
- 확인된 엔드포인트: `/v1/models`, `/v1/chat/completions`, `/v1/embeddings`,
  `/v1/messages`(Anthropic 스타일), `/v1/responses`
- 설정상 기본 모델: `mlx-community/KAT-Coder-V2.5-Dev-OptiQ-4bit`
- 앱 설정의 `maxTokens`는 2048
- **로컬 API 서버는 API 키를 요구한다.** 키 없이 또는 틀린 키로 요청하면
  HTTP 401 `{"detail":"Invalid API key"}` 가 돌아온다. 앱이 발급한 값을
  `Authorization: Bearer <키>` 헤더로 보내야 한다. 바이너리에도
  "Clients send this value as an Authorization Bearer token." 문자열이 있다.
- 키는 앱이 관리한다. 설정 파일(`Settings.plist`)에는 없다. 사용자가 앱 UI에서
  확인해 환경변수로 넘긴다. **코드나 문서에 키 값을 적지 않는다.**

### 로컬 실행 환경

- `python3` 3.9.6 (macOS 시스템 기본) — `tomllib`, `match` 등 3.10+ 문법 사용 불가
- `git` 2.50.1
- `~/.local/bin` 존재, PATH에 포함

### 대상 저장소 실태

측정 대상: `example-backend`, `example-backend-custom-x`, `org-a/example`,
`org-b/example`, `org-c/example-backend`

**diff 크기** — `example-backend` 최근 non-merge 커밋 5건: 16 / 53 / 120 / 165 / 882줄.
대부분 단일 프롬프트에 여유 있게 들어간다.

**커밋 제목 스타일이 저장소마다 다르다.**

| 스타일 | 실제 예 |
|---|---|
| 키 접두 (대괄호 없음) | `ABC-1858 Teradata 갭분석 마이그레이션 정비` |
| 대괄호 접두 | `[XYZ-248] fix: 결재 역할 팝업창 중복 제거` |
| 괄호 접미 | `fix(quality): 프로파일링 작업/테이블 삭제 시 스키마(acctId) 단위 격리 보정 (DEF-119)` |
| Conventional Commits | `ci: auto build/publish on tag push` |
| 키 없는 한국어 | `pg db업그레이드에 따른 쿼리문 변경` |

본문 언어는 대부분 한국어다. 제목 길이는 50자를 넘는 경우가 흔하다.

**브랜치명에 이슈 키가 없는 경우가 많다**: `dev`, `master`, `main`, `develop`,
`release-adv`, `fetchUserProfile`

## 3. 결정 사항

| 항목 | 결정 | 배경 |
|---|---|---|
| 통합 지점 | CLI 스크립트 | 저장소 20여 곳에 훅 복제 불필요 |
| 메시지 규칙 | 저장소 히스토리 few-shot 자동 학습 + 브랜치 이슈 키 강제 | 규칙이 저장소마다 달라 고정 포맷 불가 |
| 대상 범위 | staged 우선, 비면 worktree diff로 fallback | 일반적인 커밋 흐름과 일치 |
| LLM 호출 | 단일 호출 + diff 예산 관리 | 실측 diff가 작아 map-reduce 불필요 |
| 의존성 | 표준 라이브러리만 | venv/uv 없이 파일 하나로 이식 |

### 채택하지 않은 대안

- **map-reduce (파일별 요약 후 통합)**: 실측 diff 크기상 불필요. 로컬 30B 4bit에서
  호출 N+1회는 체감 속도를 크게 악화시킨다. 필요해지면 그때 추가한다.
- **기존 CLI(aichat 등)에 Nativ를 백엔드로 연결**: 저장소별 few-shot 자동 학습과
  이슈 키 강제 주입을 지원하지 않는다. 앞뒤로 스크립트를 붙이면 결국 같은 분량의
  코드를 짜면서 의존성만 늘어난다.
- **고정 커밋 규칙 통일**: 기존 히스토리와 충돌한다.
- **설정 파일로 저장소별 규칙 지정**: 저장소 20여 곳을 수동 등록해야 한다.
- **IntelliJ 플러그인**: 범위가 과도하게 커진다. External Tool은 커밋 메시지
  입력란에 직접 쓸 수 없어 실익이 없다.

## 4. 구조

```
~/PersonalProject/llm-gitmsg/
  README.md
  gitmsg.py                    실행 파일 겸 import 가능한 모듈
  tests/test_gitmsg.py         stdlib unittest
  docs/design.md               이 문서
  docs/decisions.md            결정 기록
  plans/implementation.md      구현 계획
~/.local/bin/gitmsg            → gitmsg.py 심볼릭 링크
```

단일 파일로 두되 테스트에서 import 할 수 있도록 `.py` 확장자를 유지하고,
PATH에는 확장자 없는 심볼릭 링크를 건다.

테스트는 하위 디렉터리에 있으므로 저장소 루트를 top-level로 지정해 실행한다.

```
python3 -m unittest discover -s tests
```

`gitmsg.py`는 표준 라이브러리만 쓰므로 가상환경이 필요 없다. 옆 프로젝트
`threads-to-pdf`와 달리 `pyproject.toml`, `uv.lock`을 두지 않는다.

### 파이프라인

```
1. 저장소 해석    cwd 또는 인자 경로 → git rev-parse --show-toplevel
2. 브랜치 확인    git branch --show-current → 이슈 키 추출 (없으면 None)
3. diff 수집      git diff --cached → 비면 git diff → 둘 다 비면 종료
4. 파일 선별      노이즈 파일은 diff 본문 제외, 파일명만 유지
5. 예산 적용      파일당 상한 → 총량 상한 순으로 큰 파일부터 절단
6. few-shot 수집  git log --no-merges
7. 프롬프트 조립
8. Nativ 호출     POST /v1/chat/completions (1회)
9. 후처리         정리 + 이슈 키 검증/삽입
10. 출력          stdout 또는 git commit -e
```

git을 호출하는 단계는 1–3, 6뿐이다. 나머지는 순수 문자열 처리이므로 독립적으로
테스트한다.

## 5. 컴포넌트

### 5.1 저장소/브랜치 해석

```
resolve_repo(path) -> str
    git -C <path> rev-parse --show-toplevel
    실패 시 "git 저장소가 아닙니다" + exit 1

current_branch(repo) -> str
    git -C <repo> branch --show-current
    detached HEAD면 빈 문자열

extract_issue_key(branch) -> str | None
    정규식 [A-Z][A-Z0-9]+-\d+ 의 첫 매치
```

`extract_issue_key` 기대 동작:

| 입력 | 출력 |
|---|---|
| `hotfix/JKL-4146` | `JKL-4146` |
| `ABC7-24` | `ABC7-24` |
| `feature/DEF-119` | `DEF-119` |
| `ABC-1858` | `ABC-1858` |
| `JKLMNO-3405` | `JKLMNO-3405` |
| `dev` / `master` / `main` / `develop` | `None` |
| `release-adv` | `None` |
| `fetchUserProfile` | `None` |
| `""` (detached) | `None` |

### 5.2 diff 수집

```
collect_diff(repo) -> (mode, files)
    mode: "staged" | "worktree"
    files: [{path, status, body}]

    git diff --cached --unified=3 가 비어 있지 않으면 mode="staged"
    아니면 git diff --unified=3 로 mode="worktree"
    둘 다 비면 exit 1 + "스테이징된 변경도, 추적 중인 변경도 없습니다."

    status는 git diff --name-status 로 별도 수집 (A/M/D/R)

    파일 단위 분할은 diff 출력의 "diff --git " 줄을 경계로 삼는다.
    각 파일의 body는 해당 경계부터 다음 경계 직전까지다.
```

### 5.3 노이즈 파일 필터

```
filter_noise_files(files) -> (kept, dropped)
```

diff 본문을 버리되 **파일명은 프롬프트에 남긴다.** 모델이 "의존성 갱신 포함"
정도는 언급할 수 있어야 한다.

제외 대상:

- `*.lock`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
- `dist/`, `build/`, `target/`, `node_modules/` 경로 **하위**
- `.idea/`, `.DS_Store`
- `*.min.js`, `*.min.css`
- git이 `Binary files ... differ`로 표시한 항목

디렉터리 이름 검사는 경로의 마지막 세그먼트를 제외하고 수행한다. 저장소 루트에
`build` 라는 이름의 스크립트 파일이 있으면 디렉터리가 아니라 파일이므로 제외하면 안 된다.

`*.sql`은 제외하지 않는다. example 계열에서는 쿼리 변경이 커밋의 핵심인 경우가
많다.

### 5.4 예산

```
apply_budget(files, per_file=6000, total=48000) -> files
```

1. 각 파일 본문을 6,000자로 자른다
2. **1단계** — 전체 합이 48,000자(대략 12k 토큰)를 넘으면, 가장 큰 파일을
   절반으로 줄이기를 반복한다. 한 파일이 200자 이하로 내려가면 그 파일은
   더 줄이지 않는다
3. **2단계** — 1단계로도 합계가 상한을 넘으면, 큰 파일부터 본문을 통째로
   `... (생략)` 로 바꾼다
4. 절단이 일어난 파일에는 잘린 자리에 `... (N줄 생략)` 표시를 남긴다.
   **이 표시는 상한 안에 포함된다** — 마커를 붙여서 상한을 넘기지 않는다

가장 큰 파일부터 줄이는 이유는 작은 파일들이 온전히 남도록 하기 위해서다.
작은 변경일수록 의도가 분명해서 메시지 품질에 더 기여한다.

2단계가 필요한 이유는 파일 수가 많은 커밋 때문이다. 코드 생성이나 대량 리네임처럼
수천 개 파일이 한 커밋에 들어오면 `200 × 파일수` 만으로도 상한을 넘어서, 1단계만으로는
예산을 지킬 수 없다. 실측하면 파일 2,000개짜리 커밋에서 합계가 상한의 4.7배까지 갔다.

**남는 한계**: 2단계까지 가도 `파일수 × len("... (생략)\n")` 아래로는 내려갈 수 없다.
파일 5,000개까지는 상한 안에 들어오고, 그보다 많으면 초과한다. 그 규모의 단일 커밋은
현실적으로 없다고 보고 여기서 멈춘다.

### 생략 줄 수 계산

`... (N줄 생략)` 의 N 은 잘려나간 부분의 개행 수에, 마지막 줄이 개행으로 끝나지
않을 때만 1을 더해 구한다. 단순히 `개행 수 + 1` 로 세면 완결된 줄만 잘렸을 때
실제보다 하나 많게 표시된다.

표시를 남기는 이유: 모델이 잘린 부분의 존재를 알아야 없는 내용을 지어내지 않는다.

### 5.5 few-shot 수집

```
collect_examples(repo, n=25) -> (subjects, full_examples)

    subjects: git log --no-merges --pretty=%s -n 25
              "Initial commit", 빈 줄 제외
    full_examples: 본문이 있는 최근 커밋 3건의 제목+본문 전문
```

본문 있는 커밋 전문을 포함하는 이유는 본문 스타일의 유일한 근거이기 때문이다.

### 5.6 키 위치 감지

```
detect_key_style(subjects) -> "bracket" | "prefix" | "suffix"

    키를 포함한 제목들을 세어 최빈값을 고른다.
    bracket: [KEY] ...
    prefix:  KEY ...
    suffix:  ... (KEY)
    키를 포함한 제목이 없으면 "prefix"
```

### 5.7 프롬프트 조립

**system**

- 커밋 메시지를 작성한다. 설명이나 잡담은 출력하지 않는다
- 출력은 커밋 메시지 그 자체다. 코드 블록으로 감싸지 않는다
- 제목 한 줄, 본문이 필요하면 빈 줄 뒤에 이어 쓴다
- 출력 언어는 설정(`--lang` / `GITMSG_LANG`)을 따른다

제목 길이 규칙은 **넣지 않는다.** 실제 히스토리에 50자를 넘는 제목이 흔하므로
관례적 길이 제한은 few-shot 예시와 충돌한다. 길이는 예시가 가르치게 둔다.

### 출력 언어

`en`(기본), `ko` 두 값을 받는다. 우선순위는 `--lang` > `GITMSG_LANG` > `en`.
모르는 값이면 유효값을 나열하고 종료 코드 1로 끝낸다 — 잘못된 설정으로 엉뚱한
언어가 나오는 것보다 즉시 알려주는 편이 낫다.

| 값 | 생성 메시지 | 도구 자체 메시지(오류·help) |
|---|---|---|
| `en` (기본) | 반드시 영어 | 영어 |
| `ko` | 반드시 한국어 | 한국어 |

한 설정이 생성 메시지와 도구 메시지를 함께 정한다. 기본값이 영어인 이유와
예전 `auto` 모드를 없앤 경위는 `decisions.md`에 적었다.

문구는 `MESSAGES` 카탈로그에 언어별로 모아둔다. 언어를 함수 인자로 끌고
다니지 않고 모듈 전역 `_LANG`을 `main()`이 한 번 정한다. CLI는 한 번
실행에 한 언어라 이 범위에서는 전역이 문제되지 않는다. 테스트는 `set_lang()`으로
직접 고정해 실행 순서에 결과가 좌우되지 않게 한다.

**user** — 네 블록:

1. 이 저장소 최근 커밋 제목 25개
2. 본문이 있는 최근 커밋 3건 전문
3. 브랜치명, 이슈 키(있으면), 키 삽입 스타일, 변경 파일 목록(상태 포함)
4. 예산을 적용한 diff

### 5.8 Nativ 클라이언트

```
list_models(url, api_key) -> [str]          GET  {url}/v1/models
complete(url, model, messages, api_key)     POST {url}/v1/chat/completions
    temperature 0.2
    max_tokens 512
    timeout 180s
    Authorization: Bearer <api_key>   (키가 있을 때만)
```

모델은 `--model` 지정이 없으면 `/v1/models` 첫 번째를 쓴다.
주소는 `--url` > `GITMSG_LLM_URL` 환경변수 > `http://127.0.0.1:8080` 순으로 결정한다.
API 키는 `--api-key` > `NATIV_API_KEY` 환경변수 순으로 결정한다. 기본값은 없다.

키를 코드에 박지 않고 환경변수로만 받는 이유는, 키가 앱이 발급한 자격 증명이라
저장소에 남으면 안 되기 때문이다. 오류 메시지에도 키 값을 출력하지 않는다.

에러 처리:

| 상황 | 처리 |
|---|---|
| Connection refused | `Nativ 로컬 API 서버가 꺼져 있습니다. Nativ 앱에서 API 서버를 켜세요.` exit 2 |
| HTTP 401 | `Nativ API 키가 없거나 올바르지 않습니다. NATIV_API_KEY 환경변수를 확인하세요.` exit 2 |
| `/v1/models` 빈 목록 | `모델이 로드되지 않았습니다.` exit 2 |
| non-200 | 상태 코드 + 응답 앞 200자, exit 2 |
| timeout | 재시도 없이 종료, exit 2 |

timeout에 재시도를 넣지 않는 이유: 대형 로컬 모델에서 재시도는 대기 시간을
두 배로 늘릴 뿐이다.

### 5.9 응답 후처리

로컬 4bit 모델은 지시에도 불구하고 출력을 감싸는 경우가 잦다. 게다가 감싸는
방식이 겹칠 때도 있다 — 따옴표로 감싼 코드펜스, 접두어 뒤에 붙은 펜스 같은
식이다. 그래서 `clean_response`는 한 번 훑고 끝내지 않고, 더 벗길 게 없는
상태(고정점)에 이를 때까지 최대 5회 반복한다.

```
clean_response(text) -> str
    반복 (최대 5회, 반복 전후로 바뀐 게 없으면 즉시 중단):
        1. "커밋 메시지:", "Commit message:" 접두 제거
        2. 코드펜스 제거 — 단, 여는/닫는 펜스가 정확히 한 쌍일 때만
        3. 감싼 따옴표 제거 — 단, 안쪽에 같은 따옴표가 없을 때만

    반복이 끝난 뒤, 미종료 펜스 정리:
        남은 펜스 런이 0개 또는 1개뿐이면(예: 닫히지 않은 여는 펜스)
        첫 줄이나 끝 줄이 펜스 마커일 때 그 줄만 제거한다. 내용은
        건드리지 않는다.

enforce_issue_key(msg, key, style) -> str
    key가 None이면 그대로 반환
    제목 줄에 key가 이미 있으면 그대로 반환
    없으면 style에 따라 삽입
```

펜스 런이 두 쌍 이상 남아 있으면, 즉 서로 다른 코드 블록이 여러 개 있으면
**펜스 벗기기만** 건너뛴다. 어느 블록이 진짜 커밋 메시지인지 판단할 근거가
없기 때문이다. 잘못 추측해 엉뚱한 블록을 메시지로 내보내는 것보다는, 사용자가
에디터에서 원문을 보고 직접 골라내는 편이 훨씬 안전하다.

접두 제거와 따옴표 제거는 이 경우에도 그대로 동작한다. 펜스 개수와 무관하게
안전한 처리이기 때문이다. 예를 들어 `커밋 메시지: ` 로 시작하고 코드 블록이
두 개 붙어 있는 응답은, 접두만 떨어지고 두 블록은 원문 그대로 남는다.

프롬프트 지시는 빗나갈 수 있지만 후처리는 빗나가지 않는다. 두 겹으로 둔다.

**키가 없으면 이 단계를 통째로 건너뛴다.** 지어낸 키가 붙는 것보다 키가 없는
편이 낫다.

### 5.10 CLI

```
gitmsg [PATH] [-e] [--model ID] [--url URL] [--print-prompt]
```

| 옵션 | 동작 |
|---|---|
| (기본) | 메시지를 stdout으로 출력 |
| `PATH` | 대상 저장소 경로. 생략 시 cwd |
| `-e`, `--edit` | `git commit -e -m <msg>` 실행. 에디터가 초안을 채운 채 열린다 |
| `--model ID` | 모델 지정 |
| `--url URL` | Nativ 주소 지정 |
| `--api-key KEY` | Nativ API 키 지정. 생략하면 `NATIV_API_KEY` 환경변수 |
| `--print-prompt` | LLM 호출 없이 조립된 프롬프트만 출력 |

`--print-prompt`는 프롬프트를 조정할 때 LLM 응답을 기다리지 않기 위한 것이다.

**자동 커밋 경로는 만들지 않는다.** `-e`는 항상 에디터를 거친다.

## 6. 테스트 전략

TDD로 진행한다. LLM 호출을 제외한 대부분이 순수 함수다.

### 단위 (네트워크·git 없음)

실제 저장소에서 관찰한 브랜치명과 커밋 제목을 픽스처로 쓴다.

- `extract_issue_key` — 5.1의 기대 동작 표 전체
- `detect_key_style` — bracket/prefix/suffix 각각, 키 없는 경우
- `filter_noise_files` — lock 파일, 바이너리, `dist/`, `*.sql` 미제외 확인
- `apply_budget` — 파일당 절단, 총량 절단, 생략 표시 삽입
- `clean_response` — 코드펜스, 따옴표, 접두 문구
- `enforce_issue_key` — 이미 있는 경우, 없어서 삽입하는 경우, key가 None인 경우

### git 연동

스크래치패드에 임시 저장소를 만들어 커밋 몇 개와 스테이징 상태를 심고
`collect_diff`, `collect_examples`를 검증한다. 실제 작업 저장소는 건드리지 않는다.

- staged 변경이 있을 때 mode="staged"
- staged가 비고 worktree 변경만 있을 때 mode="worktree"
- 둘 다 비었을 때 exit 1
- merge 커밋이 few-shot에서 제외되는지

### HTTP

`urllib` 호출부를 스텁으로 교체해 검증한다. 네트워크는 타지 않는다.

- 요청 바디에 model, messages, temperature, max_tokens가 올바르게 담기는지
- 정상 응답 파싱
- connection refused → exit 2 + 안내 문구
- non-200 → exit 2

### 수동 스모크

Nativ 서버를 켜고 실제 저장소에서 1회 실행한다. 여기서 처음으로 응답 시간을
실측한다. 현재 응답 시간에 대한 추정치는 없다.

## 7. 범위 밖

- map-reduce 기반 대형 diff 처리 (`--deep`)
- git 훅 연동
- IntelliJ 플러그인
- 브랜치 전체(base 대비) 범위 옵션
- 설정 파일
- 자동 커밋

필요해질 때 별도로 다룬다.

## 8. 전제 조건

구현과 무관하게 사용 전에 충족해야 한다.

1. Nativ 앱에서 로컬 API 서버를 켠다
2. 모델을 로드한다 (`mlx-community/KAT-Coder-V2.5-Dev-OptiQ-4bit` 권장)
3. 앱에서 API 키를 확인해 환경변수로 내보낸다

   ```bash
   export NATIV_API_KEY='...'   # 셸 설정 파일에 두려면 권한을 600 으로
   ```

4. `~/.local/bin`이 PATH에 있다
