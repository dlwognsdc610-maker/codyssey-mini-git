# Mini Git

커밋 메타데이터만 가지고 Git의 핵심 구조를 작게 다시 만든다. 파일 내용, 네트워크,
영속성은 없고 한 세션 안에서 branch, commit DAG, graph search, inverted index,
직접 구현한 정렬만 본다.

## 구조

컴파일러의 SSA/use-def 자료구조처럼 보면 단순하다.

```text
commits[hash] = Commit          commit table
Commit.parents                  parent(def) edge
children[parent] = children     reverse edge / use-list
branches[name] = commit hash    branch head
HEAD = current branch
```

새 commit은 현재 branch head를 parent로 잡는다. commit table, parent/children edge,
keyword/author index를 갱신한 뒤 branch head를 새 hash로 옮긴다. 이미 존재하는
commit만 parent로 잡으므로 이 경로에서는 cycle이 생기지 않고 commit graph는 DAG로
유지된다.

각 commit은 아래 필드만 가진다.

```text
hash, message, author, timestamp, parents
```

hash는 세션 안에서 증가 counter를 7자리 hex로 표현한다. 암호학적 hash가 목적이
아니라 commit을 빠르게 식별하는 unique key가 목적이다.

## 알고리즘

`LOG`는 Kahn 방식으로 indegree가 0인 commit부터 꺼내서 **parent가 child보다 항상
먼저** 나오게 한다. 준비된 commit을 최소 힙에 두고 hash가 작은 것부터 꺼낸다.
꺼낸 commit의 children마다 남은 parent 수를 하나 줄이고, 0이 된 child를 힙에 넣는다.

`PATH a b`는 parent edge를 무방향으로 본다. `parents + children`을 이웃으로 두고
BFS를 사용하므로 간선 수가 가장 작은 경로가 나온다. 같은 길이의 경로에서는 hash
순서로 이웃을 방문해 문자열 기준으로 더 작은 경로를 먼저 고른다. 첫 방문 때 이전
commit을 기록하고, 목적지에 도착하면 그 연결을 거슬러 올라가 경로를 복원한다.

`ANCESTORS`는 한 commit에서 parent chain만 따라가 조상을 모은다. 그 집합에 Kahn
순회를 적용해 parent-first 결과를 만든다. `children`은 역방향 edge라 PATH에서
양방향 탐색할 때 쓴다.

검색할 때 commit 전체를 다시 훑지 않는다.

```text
keyword -> [commit hash, ...]
author  -> [commit hash, ...]
```

message는 `lower().split()`한 token을 keyword index에 넣는다. 여러 단어를 검색하면
각 token 후보의 교집합만 본다.

정렬은 Python `sorted()`와 `list.sort()`를 쓰지 않고 stable merge sort를 직접
구현했다. 평균/최악 모두 O(n log n), 추가 공간 O(n), stable sort다. `date`와
`author`는 같은 sort 함수에 비교 key만 바꿔서 처리한다.

## 실행

```sh
python3 main.py
```

예:

```text
mini-git> init "Alice"
Initialized repository.
Current branch: main
Current user: Alice

mini-git> commit "Initial commit"
[main 0000001] Initial commit

mini-git> branch feature
Created branch: feature

mini-git> switch feature
Switched to branch: feature

mini-git> commit "Add login feature"
[feature 0000002] Add login feature
```

명령은 대소문자를 구분하지 않는다.

```text
INIT <user_name>
BRANCH <branch_name>
SWITCH <branch_name>
COMMIT <message>
LOG
LOG --sort-by=date
LOG --sort-by=author
PATH <commit1> <commit2>
ANCESTORS <commit_hash>
SEARCH <keyword>
SEARCH --author=<name>
exit / quit
```

공백이 들어가는 문자열은 따옴표로 감싼다.

## 검사

```sh
python3 cts.py
```

CTS는 branch head, parent-first log, keyword/author index, ancestors, BFS path,
quoted CLI, error path, stable merge sort와 `sorted()`/`.sort()` 미사용을 확인한다.
명령별 상태 변화와 조회·오류 뒤 상태 보존, 빈 branch에서 생긴 독립 root,
다중 parent와 여러 조회의 조합도 검사한다.
실행 결과는 `cts-report.json`에 남는다. 1–3시간 평가 전 복습 순서, 설명 질문,
선택 확장 범위와 현재 검증 결과는 [CTS_REVIEW.md](CTS_REVIEW.md)에 있다.
