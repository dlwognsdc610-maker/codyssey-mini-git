# Mini Git CTS · 평가 전 자기 점검

이 CTS는 **Codyssey 공식 채점기나 PASS 예측이 아니다.** 확인한 근거는 이 폴더의 [README](README.md)와 self-os의 `Docs/codyssey/codyssey-orientation.md`다. 오리엔테이션에는 Mini Git의 DAG·그래프·탐색·정렬 목표만 있고, LMS의 상세 채점표는 이 로컬 자료에서 확인되지 않았다. `cts.py`의 `basis=local CLI behavior` 항목은 현재 CLI가 약속하는 오류 응답과 상태 보존을 살핀다. 실제 평가 전에 LMS 원문과 서로 다른 부분이 있는지 확인해.

## 한 번에 실행

```sh
cd /home/ljh/self-os/Codyssey/mini-git
python3 cts.py
```

종료 코드 0은 선택한 로컬 항목이 전부 PASS, 1은 FAIL 또는 SKIP이 있다는 뜻이다. 결과는 [cts-report.json](cts-report.json)에 기록된다. 각 항목은 ID·단계·근거·결과·실패 이유를 남기고 검사 대상 `main.py`의 SHA-256도 기록한다. `--source 다른/main.py`로 별도 후보를 검사할 수 있다. CTS는 검사 대상 파일을 임시 디렉터리에 복사해서 실행하며 실제 `.git`, 작업 파일, 저장소 상태를 수정하지 않는다. 선택 확장은 `python3 cts.py --stretch`로 실행한다.

2026-10-06 현재 원본에 `python3 cts.py --stretch`를 실행한 결과: **PASS 24 · FAIL 0 · SKIP 0**. 기본 23개와 선택 확장 1개가 모두 통과했다. `@dataclass`를 `class Commit` 바로 앞으로 옮겨 문법 오류를 고쳤고, commit 상태 갱신 순서와 LOG·PATH·ANCESTORS 순회를 정리한 실제 `main.py`를 검사했다.

## 1–3시간 복습 경로

시간은 프로그램 실행 시간이 아니라 평가 전 직접 추적하고 설명하는 데 쓰는 시간이다.

| 공부 시간 | 실행 | 직접 확인할 것 |
|---|---|---|
| 1시간 | `python3 cts.py --stage 1` | `INIT → COMMIT → BRANCH → SWITCH → COMMIT`의 head와 parent를 종이에 그린다. 기본 `LOG`가 왜 parent를 먼저 출력하는지 말로 설명한다. |
| 2시간 | `python3 cts.py --stage 2` | 다른 branch의 commit으로 가는 `PATH`를 BFS 큐 순서로 추적한다. `ANCESTORS`는 parent만 따르고, keyword 검색은 `lower().split()` token 교집합을 쓰는 이유를 확인한다. 재초기화·중복 branch·없는 hash 뒤 상태도 살핀다. |
| 3시간 | `python3 cts.py --stage 3` | timestamp를 일부러 뒤집어 `date` 정렬을 확인하고 author 정렬 및 stable merge sort를 설명한다. 원하면 `--stretch`로 CLI가 만들지 않는 다중 parent DAG를 주입한 경로 동률 사례도 본다. |

매 단계는 그 이전 단계도 함께 실행한다. 오류가 나오면 JSON의 첫 `FAIL`을 보고 해당 상태 전이와 인덱스 갱신 지점을 찾으면 돼. 수정 후 같은 명령으로 재검사하고, 무엇을 고쳤는지 스스로 설명해 봐.

## 평가에서 설명해 볼 질문

1. 새 commit의 parent는 언제 확정되고, branch head는 언제 바뀌나? 다른 branch head는 왜 그대로인가?
2. `children`은 `parents`와 어떤 관계이며 `PATH`에는 왜 둘 다 필요한가? `ANCESTORS`에는 왜 parent만 필요한가?
3. BFS가 최소 간선 경로를 보장하는 조건은 무엇인가? 다중 parent의 동률 경로에서는 이 구현이 어떤 이웃을 먼저 고르나?
4. `SEARCH login`은 `logins`를 찾나? 대소문자와 중복 token, 여러 token을 현재 코드가 각각 어떻게 처리하나?
5. `LOG` 기본 순서와 `--sort-by=date`, `--sort-by=author`의 기준은 어떻게 다른가? stable merge sort에서 비교가 `<=`인 이유는 무엇인가?
6. `INIT`을 다시 하면 commit hash `0000001`이 재사용될 수 있다. 이 hash의 유일성 범위는 어디까지인가?

## CTS 자체 점검 기록

- 변경 전 원본 `main.py`: 문법 오류를 정확히 FAIL로 기록하고 의존 항목은 SKIP으로 기록했다.
- 원본을 임시 디렉터리에 복사해, 이미 제안된 `@dataclass` 위치 수정 **한 곳만** 적용한 진단 후보: 기본 23/23, `--stretch` 포함 24/24 PASS. 이것은 원본 PASS가 아니다.
- 별도 임시 후보에서 branch 생성 시 head 복사를 망가뜨리자 `branch_fork` 등에서 실패했고, merge sort의 `<=`를 `<`로 바꾸자 `stable_merge_sort`에서 실패했다. 두 경우 모두 CTS 종료 코드 1을 확인했다.
- 현재 원본 `main.py`: 기존 CTS의 `--stretch` 포함 24/24 PASS, 종료 코드 0을 확인했다.

필수 기능을 넘어서는 `multiparent_tie_break`는 **선택 확장**이다. 현재 CLI에는 merge 명령이 없어 다중 parent 상태를 직접 만들 수 없기 때문이다. 이 항목은 내부 자료구조에 두 번째 parent를 주입해 README의 경로 동률 설명을 점검한다.
