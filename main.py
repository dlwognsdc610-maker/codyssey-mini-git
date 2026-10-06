#!/usr/bin/env python3
"""Mini Git: an in-memory commit DAG with branches, search indexes and CLI."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from heapq import heappop, heappush
import shlex
import time


"""
commit {
 - hash
 - message
 - author
 - timestamp
 - parent
}

Simply set relations:
   commit
   branch
   commit addressed as ssa-like structures.

   if (somethings that changed):
      always consider it default as ssa-form.
      so always new commits inserted,
      it's def come from once.

   This assume simplify the it' define always once,
   so it don't require entire state tracking
   and avoid self-dependencies in file log.
   

"""
@dataclass
class Commit:
    """One immutable commit node in the DAG."""
    hash: str
    message: str
    author: str
    timestamp: float
    parents: list[str]


def merge_sort(items, key):
    #Stable O(n log n) merge sort without sorted() or list.sort().

    # Basis.
    if len(items) <= 1:
        return items[:]

    mid = len(items) // 2

    # Recurise walk.
    left = merge_sort(items[:mid], key)
    right = merge_sort(items[mid:], key)
    result = []
    i = 0
    j = 0


    #Invariant:
    #   we recursivly tracking bisected sort state,
    #   so left block and right block was already sorted.
    #   Then, we only-check it's new structures only.
    while i < len(left) and j < len(right):
        if key(left[i]) <= key(right[j]):
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    while i < len(left):
        result.append(left[i])
        i += 1

    while j < len(right):
        result.append(right[j])
        j += 1

    return result


class MiniGit:
    """Repository state and graph/index algorithms for the Mini Git commands."""

    def __init__(self):
        # Null state.
        self.initialized = False
        self.user = None
        self.current_branch = None
        self.branches = {}

        # hash -> Commit is the def table.
        self.commits = {}
        # parent -> children is the reverse edge/use-list.
        self.children = {}

        self.keyword_index = {}
        self.author_index = {}
        self.next_id = 1

    def init(self, user_name):
        self.initialized = True
        self.user = user_name
        self.current_branch = "main"
        self.branches = {"main": None}
        self.commits = {}
        self.children = {}
        self.keyword_index = {}
        self.author_index = {}
        self.next_id = 1
        return [
            "Initialized repository.",
            "Current branch: main",
            f"Current user: {user_name}",
        ]

    def _new_hash(self):
        # Counter based and therefore unique inside one repository session.
        value = f"{self.next_id:07x}"
        self.next_id += 1
        return value

    def _index_commit(self, commit):
        author = commit.author.lower()
        self.author_index.setdefault(author, []).append(commit.hash)

        seen = set()
        for token in commit.message.lower().split():
            if token in seen:
                continue
            seen.add(token)
            self.keyword_index.setdefault(token, []).append(commit.hash)

    def commit(self, message):
        # State walk:
        #   old head(1) <-- new(2)     parents
        #   old head(1) --> new(2)     children
        #   node -> edges -> index -> move head.
        parent = self.branches[self.current_branch]
        parents = [] if parent is None else [parent]
        commit_hash = self._new_hash()
        node = Commit(commit_hash, message, self.user, time.time(), parents)

        self.commits[commit_hash] = node
        self.children.setdefault(commit_hash, set())
        for parent_hash in parents:
            self.children.setdefault(parent_hash, set()).add(commit_hash)

        self._index_commit(node)
        self.branches[self.current_branch] = commit_hash
        return f"[{self.current_branch} {commit_hash}] {message}"

    def branch(self, name):
        if name in self.branches:
            return f"Branch already exists: {name}"
        # Copy the head value:
        #   main ----+--> 1
        #   feature -+
        #   later commit moves only the selected branch head.
        self.branches[name] = self.branches[self.current_branch]
        return f"Created branch: {name}"

    def switch(self, name):
        if name not in self.branches:
            return f"Unknown branch: {name}"
        # Select which branch head the next commit will move.
        self.current_branch = name
        return f"Switched to branch: {name}"

    def _topological_commits(self, commit_hashes=None):
        """Return commits parent-first over the selected subgraph (Kahn)."""
        # Forward walk (parent -> child):
        #   1 --> 2 --+
        #   |        |
        #   +--> 3 --+--> 4
        #   remaining parents of 4: 2 -> 1 -> 0.
        #   ready when all its parent edges are processed.
        if commit_hashes is None:
            commit_hashes = self.commits

        indegree = {}
        for commit_hash in commit_hashes:
            node = self.commits[commit_hash]
            indegree[commit_hash] = sum(parent in commit_hashes for parent in node.parents)

        ready = []
        for commit_hash, degree in indegree.items():
            if degree == 0:
                heappush(ready, commit_hash)

        result = []
        # Invariant at the loop boundary:
        #   ready holds every unvisited node with indegree=0.
        #   indegree and ready are local walk state.
        while ready:
            current = heappop(ready)
            result.append(self.commits[current])

            for child in self.children.get(current, set()):
                if child not in indegree:
                    continue
                indegree[child] -= 1
                if indegree[child] == 0:
                    heappush(ready, child)

        return result

    def log(self, sort_by=None):
        nodes = self._topological_commits()
        if sort_by == "date":
            nodes = merge_sort(nodes, lambda node: (node.timestamp, node.hash))
        elif sort_by == "author":
            nodes = merge_sort(nodes, lambda node: (node.author.lower(), node.timestamp, node.hash))
        return nodes

    def _neighbors(self, commit_hash):
        node = self.commits[commit_hash]
        result = node.parents[:]
        for child in self.children.get(commit_hash, set()):
            result.append(child)
        return merge_sort(result, lambda value: value)

    def path(self, start, end):
        """Shortest undirected commit path; lexicographically smallest on ties."""
        if start not in self.commits:
            return None, f"Unknown commit: {start}"
        if end not in self.commits:
            return None, f"Unknown commit: {end}"

        # Example fork: 2 <-- 1 --> 3 (parent -> child).
        # BFS walk:
        #   queue:    [2] -> [1] -> [3]
        #   previous:  3 -> 1 -> 2 -> None
        #   reverse it -> path [2,1,3].
        queue = deque([start])
        previous = {start: None}

        while queue:
            current = queue.popleft()
            if current == end:
                path = []
                while current is not None:
                    path.append(current)
                    current = previous[current]
                return path[::-1], None

            for neighbor in self._neighbors(current):
                if neighbor in previous:
                    continue
                # First visit defines the previous edge once.
                previous[neighbor] = current
                queue.append(neighbor)

        return [], None

    def ancestors(self, commit_hash):
        if commit_hash not in self.commits:
            return None

        # Parent walk:
        #   2 <-- 1 --> 3 --> 4       parent -> child
        #   start from 4: 4 -> 3 -> 1.
        #   found={1,3}; sibling 2 stays outside this set.
        found = set()
        stack = self.commits[commit_hash].parents[:]
        while stack:
            current = stack.pop()
            if current in found:
                continue
            found.add(current)
            for parent in self.commits[current].parents:
                stack.append(parent)

        # Parent-first makes the result easier to read.
        return self._topological_commits(found)

    def search_keyword(self, query):
        tokens = query.lower().split()
        if not tokens:
            return []

        first = self.keyword_index.get(tokens[0], [])
        # Candidate walk, e.g. "main change":
        #   main {3,4} & change {2,3} -> {3}.
        candidates = set(first)
        for token in tokens[1:]:
            candidates &= set(self.keyword_index.get(token, []))

        nodes = [self.commits[commit_hash] for commit_hash in candidates]
        return merge_sort(nodes, lambda node: (node.timestamp, node.hash))

    def search_author(self, author):
        hashes = self.author_index.get(author.lower(), [])
        nodes = [self.commits[commit_hash] for commit_hash in hashes]
        return merge_sort(nodes, lambda node: (node.timestamp, node.hash))


def format_commit(node, repo):
    stamp = datetime.fromtimestamp(node.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    labels = []
    for name, commit_hash in repo.branches.items():
        if commit_hash == node.hash:
            labels.append(name)
    labels = merge_sort(labels, lambda value: value)
    suffix = f" [{' '.join(labels)}]" if labels else ""
    return f"commit {node.hash} ({node.author}, {stamp}){suffix}\n{node.message}"


def print_commits(nodes, repo):
    if not nodes:
        print("No commits.")
        return
    for i, node in enumerate(nodes):
        if i:
            print()
        print(format_commit(node, repo))


def invalid_args():
    print("Invalid args")


# Loop:
def repl():
    repo = MiniGit()

    while True:
        try:
            line = input("mini-git> ")
        except EOFError:
            # No op.
            break

        try:
            args = shlex.split(line)
        except ValueError:
            invalid_args()
            continue

        if not args:
            continue

        command = args[0].upper()
        if command in ("EXIT", "QUIT") and len(args) == 1:
            break

        if command == "INIT":
            if len(args) != 2:
                invalid_args()
                continue
            for text in repo.init(args[1]):
                print(text)
            continue

        if not repo.initialized:
            print("Repository not initialized.")
            continue

        if command == "BRANCH":
            if len(args) != 2:
                invalid_args()
            else:
                print(repo.branch(args[1]))

        elif command == "SWITCH":
            if len(args) != 2:
                invalid_args()
            else:
                print(repo.switch(args[1]))

        elif command == "COMMIT":
            if len(args) != 2:
                invalid_args()
            else:
                print(repo.commit(args[1]))

        elif command == "LOG":
            if len(args) == 1:
                print_commits(repo.log(), repo)
            elif len(args) == 2 and args[1].lower() in ("--sort-by=date", "--sort-by=author"):
                print_commits(repo.log(args[1].split("=", 1)[1].lower()), repo)
            else:
                invalid_args()

        elif command == "PATH":
            if len(args) != 3:
                invalid_args()
                continue
            path, error = repo.path(args[1], args[2])
            if error:
                print(error)
            elif not path:
                print("No path")
            else:
                print("Path: " + " -> ".join(path))

        elif command == "ANCESTORS":
            if len(args) != 2:
                invalid_args()
                continue
            nodes = repo.ancestors(args[1])
            if nodes is None:
                print(f"Unknown commit: {args[1]}")
            else:
                print_commits(nodes, repo)

        elif command == "SEARCH":
            if len(args) != 2:
                invalid_args()
                continue
            if args[1].lower().startswith("--author="):
                author = args[1].split("=", 1)[1]
                nodes = repo.search_author(author)
            else:
                nodes = repo.search_keyword(args[1])
            print_commits(nodes, repo)

        else:
            print(f"Unknown command: {args[0]}")


#Entry point.
if __name__ == "__main__":
    repl()
