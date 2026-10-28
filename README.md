# llm-gitmsg

Nativ 앱에 로드한 로컬 LLM으로 git 커밋 메시지 초안을 만드는 CLI.

저장소의 기존 커밋 히스토리를 few-shot 예시로 삼아 그 저장소의 스타일에 맞춘다.
브랜치명에 이슈 키가 있으면 제목에 반드시 들어가게 보장한다.

## 전제 조건

1. Nativ 앱에서 **로컬 API 서버를 켠다**
2. 모델을 로드한다 (`mlx-community/KAT-Coder-V2.5-Dev-OptiQ-4bit` 권장)
3. 앱에서 API 키를 확인해 환경변수로 내보낸다

   ```bash
   export NATIV_API_KEY='...'
   ```

   키는 이 저장소 어디에도 저장하지 않는다. 셸 설정 파일에 둔다면 권한을 `600`으로 둔다.
   평소에는 `--api-key`로 직접 넘기지 말고 이 환경변수를 쓴다 — 커맨드라인 인자로 넘기면
   `ps` 출력과 셸 히스토리에 키가 그대로 남는다.
4. `~/.local/bin`이 PATH에 있다

Python은 macOS 기본 `python3`면 된다. 외부 의존성이 없어 가상환경도 필요 없다.

## 언어 설정

출력 언어는 `en`(기본)과 `ko` 중에서 고른다. 안내 문구와 커밋 메시지가 모두
이 설정을 따른다.

```bash
gitmsg                    # 영어로 (기본)
gitmsg --lang ko          # 이번 한 번만 한국어로
export GITMSG_LANG=ko     # 항상 한국어로
```

| 값 | 커밋 메시지 | 안내·오류·도움말 |
|---|---|---|
| `en` (기본) | 영어로 고정 | 영어 |
| `ko` | 한국어로 고정 | 한국어 |

저장소 히스토리가 한국어여도 옵션을 주지 않으면 영어로 나온다. 한국어 저장소를
주로 다룬다면 `GITMSG_LANG=ko`를 셸 설정에 넣어 두는 편이 편하다.

다른 언어를 추가하려면 `gitmsg.py`의 `MESSAGES` 딕셔너리에 키를 하나 더 넣고
`SUPPORTED_LANGS`에 코드를 추가하면 된다. 두 언어의 키 집합과 `%s`/`%d` 개수가
일치하는지는 테스트가 검사한다.

## 설치

```bash
git clone <저장소> ~/PersonalProject/llm-gitmsg
cd ~/PersonalProject/llm-gitmsg
chmod +x gitmsg.py
ln -sf "$PWD/gitmsg.py" ~/.local/bin/gitmsg
```

## 사용

```bash
# 현재 저장소의 스테이징된 변경으로 메시지 초안 출력
gitmsg

# 다른 저장소를 대상으로
gitmsg ~/work/team-a/example-backend

# 에디터에 초안을 채운 채 커밋 창 열기
gitmsg -e

# 프롬프트만 확인 (모델 호출 없음)
gitmsg --print-prompt
```

실행하면 대상 프로젝트 경로와 진행 상황을 먼저 보여 주고, 끝나면 결과를 따로 구분해 출력한다.

```
Project: /Users/me/work/example-backend
Analyzing changes...

Suggested commit message:
ABC-102 Handle missing user in findById
```

안내 문구는 stderr로, 커밋 메시지만 stdout으로 나간다. 그래서 `gitmsg | pbcopy`처럼
파이프로 넘기면 메시지만 복사된다.

| 옵션 | 설명 |
|---|---|
| `PATH` | 대상 저장소 경로. 생략하면 현재 디렉터리 |
| `-e`, `--edit` | `git commit -e`로 에디터를 연다 |
| `--model ID` | 모델 지정. 생략하면 로드된 첫 번째 |
| `--url URL` | Nativ 주소. `GITMSG_URL` 환경변수로도 지정 가능 |
| `--api-key KEY` | Nativ API 키. 생략하면 `NATIV_API_KEY` 환경변수. 평소 사용에는 권장하지 않음 — `ps`와 셸 히스토리에 노출됨 |
| `--lang {en,ko}` | 출력 언어. 생략하면 `GITMSG_LANG` 환경변수, 그것도 없으면 `en` |
| `--print-prompt` | 조립된 프롬프트만 출력하고 끝낸다 |

## 동작

1. `git diff --cached`를 먼저 본다. 비어 있으면 `git diff`로 내려간다
2. lock 파일, 빌드 산출물, 바이너리는 diff 본문을 빼고 파일명만 남긴다
3. 파일당 6,000자 / 전체 48,000자 예산 안에 맞춘다
4. 최근 커밋 25건의 제목과, 본문이 있는 커밋 3건을 예시로 붙인다
5. `/v1/chat/completions`를 한 번 호출한다
6. 코드 블록·따옴표를 벗기고, 이슈 키가 빠졌으면 붙인다

## 실측 (2026-09-15, Apple Silicon Mac)

모델: `mlx-community/KAT-Coder-V2.5-Dev-OptiQ-4bit` (Nativ 0.3.7)

| diff 규모 | 생성 시간 |
|---|---|
| 1파일 2줄 (제목만 생성) | 5.6초 |
| 1파일 약 15줄 (제목 + 본문 3줄) | 57초 |

편차가 큽니다. 프롬프트 길이보다 **생성할 토큰 수**가 시간을 좌우합니다. 본문까지
쓰는 커밋이면 1분 가까이 걸린다고 보는 편이 안전합니다. 급하면 먼저 돌려놓고
다른 일을 하다 오는 쪽이 낫습니다.

실제 생성 예 (브랜치 `feature/ABC-102`, 히스토리에 `ABC-100 ...` 접두 스타일):

```
ABC-102 findById 예외 처리 및 사용자 잠금 기능 추가

- findById: null 반환 대신 UserNotFoundException 던지도록 변경
- lock: 사용자 잠금 설정 메서드 추가
```

브랜치에서 뽑은 이슈 키가 히스토리와 같은 접두 스타일로 붙었고, 본문 언어도
저장소 히스토리를 따라 한국어로 나왔습니다.

## 종료 코드

| 코드 | 의미 |
|---|---|
| 0 | 성공 |
| 1 | 저장소가 아니거나 변경이 없음 |
| 2 | Nativ 서버·인증·모델 문제 |

`-e`를 쓰면 이 규칙에서 벗어난다 — `main`이 `git commit`의 종료 코드를 그대로 돌려주므로, pre-commit 훅이 거부하거나 에디터를 그냥 닫아 커밋을 취소해도 1이 나올 수 있다.

## 테스트

```bash
python3 -m unittest discover -s tests -v
```

네트워크와 실제 저장소를 타지 않는다. git 연동 테스트는 임시 저장소를 만들어 쓴다.

## 설계 문서

- `docs/design.md` — 설계
- `docs/decisions.md` — 결정 기록
- `plans/2026-09-14-gitmsg.md` — 구현 계획
