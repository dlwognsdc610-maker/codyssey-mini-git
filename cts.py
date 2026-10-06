#!/usr/bin/env python3
"""Mini Git local conformance and review suite (not an official Codyssey grader)."""

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
CASES = []


def case(name, stage, basis="README", optional=False):
    def register(fn):
        CASES.append((name, stage, basis, optional, fn))
        return fn
    return register


def equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def true(value, label):
    if not value:
        raise AssertionError(label)


def ids(nodes):
    return [node.hash for node in nodes]


def new_repo(ctx, user="Alice"):
    repo = ctx["module"].MiniGit()
    repo.init(user)
    return repo


def fork(ctx):
    repo = new_repo(ctx)
    repo.commit("base")
    base = repo.branches["main"]
    repo.branch("feature")
    repo.switch("feature")
    repo.commit("feature change")
    feature = repo.branches["feature"]
    repo.switch("main")
    repo.commit("main change")
    main = repo.branches["main"]
    return repo, base, feature, main


def session(ctx, commands):
    proc = subprocess.run(
        [sys.executable, str(ctx["copy"])],
        cwd=ctx["temp"],
        input="\n".join([*commands, "quit", ""]),
        text=True,
        capture_output=True,
        timeout=5,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    equal(proc.returncode, 0, "CLI exit status; stderr=" + proc.stderr)
    equal(proc.stderr, "", "CLI stderr")
    return proc.stdout.replace("mini-git> ", "")


@case("init_empty", 1)
def _(ctx):
    repo = ctx["module"].MiniGit()
    equal(repo.initialized, False, "initial state")
    lines = repo.init("Alice")
    equal(lines, ["Initialized repository.", "Current branch: main", "Current user: Alice"], "init response")
    equal(repo.branches, {"main": None}, "initial branch")
    equal(repo.log(), [], "empty log")


@case("first_commit", 1)
def _(ctx):
    repo = new_repo(ctx)
    result = repo.commit("first")
    node = repo.commits[repo.branches["main"]]
    equal(node.hash, "0000001", "first hash")
    equal(node.parents, [], "root parents")
    equal((node.author, node.message), ("Alice", "first"), "metadata")
    equal(result, "[main 0000001] first", "commit response")


@case("commit_chain", 1)
def _(ctx):
    repo = new_repo(ctx)
    repo.commit("one")
    repo.commit("two")
    equal(repo.branches["main"], "0000002", "head advanced")
    equal(repo.commits["0000002"].parents, ["0000001"], "parent link")
    equal(repo.children["0000001"], {"0000002"}, "reverse link")


@case("branch_fork", 1)
def _(ctx):
    repo, base, feature, main = fork(ctx)
    equal((base, feature, main), ("0000001", "0000002", "0000003"), "branch heads")
    equal(repo.current_branch, "main", "selected branch")
    equal(repo.commits[feature].parents, [base], "feature parent")
    equal(repo.commits[main].parents, [base], "main parent")


@case("default_log_parent_first", 1)
def _(ctx):
    repo, base, feature, main = fork(ctx)
    ordered = ids(repo.log())
    equal(ordered, [base, feature, main], "default log")
    for node in repo.log():
        for parent in node.parents:
            true(ordered.index(parent) < ordered.index(node.hash), "parent must precede child")


@case("quoted_case_insensitive_cli", 1)
def _(ctx):
    output = session(ctx, ['INIT "Alice Kim"', 'CoMmIt "Initial commit"', 'BrAnCh feature', 'sWiTcH feature'])
    for expected in ("Current user: Alice Kim", "[main 0000001] Initial commit", "Created branch: feature", "Switched to branch: feature"):
        true(expected in output, f"CLI missing {expected!r}")


@case("cli_log_search", 1)
def _(ctx):
    output = session(ctx, ['init "Alice Kim"', 'commit "Initial commit"', 'commit "Add login feature"', 'log', 'search login', 'search --author="Alice Kim"'])
    true("commit 0000001" in output and "commit 0000002" in output, "log omitted commit")
    true(output.count("Add login feature") >= 3, "log/search results missing")
    true("Initial commit" in output, "author search omitted first commit")


@case("reinit_clears_session", 2)
def _(ctx):
    repo = new_repo(ctx)
    repo.commit("old")
    repo.branch("old-branch")
    repo.init("Bob")
    equal(repo.branches, {"main": None}, "branches after reinit")
    equal(repo.commits, {}, "commits after reinit")
    equal(repo.search_keyword("old"), [], "index after reinit")
    repo.commit("new")
    equal(repo.branches["main"], "0000001", "counter after reinit")
    equal(repo.commits["0000001"].author, "Bob", "new author")


@case("duplicate_branch_keeps_head", 2, "local CLI behavior")
def _(ctx):
    repo = new_repo(ctx)
    repo.commit("base")
    repo.branch("feature")
    repo.switch("feature")
    repo.commit("next")
    before = dict(repo.branches)
    equal(repo.branch("feature"), "Branch already exists: feature", "duplicate error")
    equal(repo.branches, before, "duplicate branch changed head")


@case("unknown_switch_keeps_state", 2, "local CLI behavior")
def _(ctx):
    repo = new_repo(ctx)
    before = (repo.current_branch, dict(repo.branches))
    equal(repo.switch("missing"), "Unknown branch: missing", "switch error")
    equal((repo.current_branch, repo.branches), before, "unknown switch changed state")


@case("ancestors_parent_only", 2)
def _(ctx):
    repo, base, feature, main = fork(ctx)
    equal(ids(repo.ancestors(feature)), [base], "feature ancestors")
    equal(ids(repo.ancestors(main)), [base], "main ancestors")
    equal(ids(repo.ancestors(base)), [], "root ancestors")
    true(feature not in ids(repo.ancestors(main)), "sibling became ancestor")


@case("path_cross_branch_shortest", 2)
def _(ctx):
    repo, base, feature, main = fork(ctx)
    path, error = repo.path(feature, main)
    equal(error, None, "path error")
    equal(path, [feature, base, main], "shortest undirected path")


@case("path_self_and_unknown", 2)
def _(ctx):
    repo = new_repo(ctx)
    repo.commit("one")
    equal(repo.path("0000001", "0000001"), (["0000001"], None), "identity path")
    equal(repo.path("bad", "0000001"), (None, "Unknown commit: bad"), "unknown start")
    equal(repo.path("0000001", "bad"), (None, "Unknown commit: bad"), "unknown end")
    equal(repo.ancestors("bad"), None, "unknown ancestors")


@case("keyword_exact_token", 2)
def _(ctx):
    repo = new_repo(ctx)
    repo.commit("Login login API")
    repo.commit("logins only")
    equal(ids(repo.search_keyword("LOGIN")), ["0000001"], "case-insensitive exact token")
    equal(ids(repo.search_keyword("log")), [], "substring must not match")
    equal(repo.keyword_index["login"], ["0000001"], "repeated token should be indexed once")


@case("keyword_intersection", 2)
def _(ctx):
    repo = new_repo(ctx)
    repo.commit("login API")
    repo.commit("login UI")
    repo.commit("API docs")
    equal(ids(repo.search_keyword("API login")), ["0000001"], "two-token intersection")
    equal(ids(repo.search_keyword("login API")), ["0000001"], "token order")
    equal(repo.search_keyword("login missing"), [], "unknown token")


@case("author_exact_casefold", 2)
def _(ctx):
    repo = new_repo(ctx, "Alice Kim")
    repo.commit("one")
    repo.user = "Bob"
    repo.commit("two")
    equal(ids(repo.search_author("aLiCe KiM")), ["0000001"], "author casefold")
    equal(repo.search_author("Alice"), [], "partial author")


@case("empty_results", 2)
def _(ctx):
    repo = new_repo(ctx)
    equal(repo.search_keyword(""), [], "empty query")
    equal(repo.search_author("nobody"), [], "unknown author")
    equal(repo.log(), [], "empty log")
    output = session(ctx, ["init Alice", "log", "search missing"])
    equal(output.count("No commits."), 2, "empty CLI results")


@case("cli_errors_and_arity", 2, "local CLI behavior")
def _(ctx):
    output = session(ctx, ["commit before", "init", "init Alice", "commit", "branch", "switch nope", "path bad worse", "ancestors bad", "search", "log --sort-by=wrong", "wat", "log"])
    true("Repository not initialized." in output, "pre-init error")
    true(output.count("Invalid args") >= 5, "arity errors")
    for expected in ("Unknown branch: nope", "Unknown commit: bad", "Unknown command: wat", "No commits."):
        true(expected in output, f"missing error/result {expected!r}")


@case("sort_date", 3)
def _(ctx):
    repo = new_repo(ctx)
    for message in ("a", "b", "c"):
        repo.commit(message)
    repo.commits["0000001"].timestamp = 30
    repo.commits["0000002"].timestamp = 10
    repo.commits["0000003"].timestamp = 20
    equal(ids(repo.log("date")), ["0000002", "0000003", "0000001"], "date order")


@case("sort_author", 3)
def _(ctx):
    repo = new_repo(ctx, "Zed")
    repo.commit("one")
    repo.user = "alice"
    repo.commit("two")
    repo.user = "Bob"
    repo.commit("three")
    for i, node in enumerate(repo.commits.values()):
        node.timestamp = i
    equal(ids(repo.log("author")), ["0000002", "0000003", "0000001"], "author order")


@case("stable_merge_sort", 3)
def _(ctx):
    source = [(1, "first"), (0, "earlier"), (1, "second"), (1, "third")]
    output = ctx["module"].merge_sort(source, lambda item: item[0])
    equal(output, [(0, "earlier"), (1, "first"), (1, "second"), (1, "third")], "stable order")
    equal(source, [(1, "first"), (0, "earlier"), (1, "second"), (1, "third")], "input preservation")
    equal(ctx["module"].merge_sort([], lambda x: x), [], "empty sort")


@case("no_builtin_sort_calls", 3)
def _(ctx):
    tree = ast.parse(ctx["copy"].read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "sorted":
            offenders.append(f"sorted() at line {node.lineno}")
        if isinstance(node.func, ast.Attribute) and node.func.attr == "sort":
            offenders.append(f".sort() at line {node.lineno}")
    equal(offenders, [], "built-in sorting calls")


@case("multiparent_tie_break", 3, "README internal DAG claim", optional=True)
def _(ctx):
    repo, base, feature, main = fork(ctx)
    repo.commit("synthetic merge")
    merge = repo.branches["main"]
    repo.commits[merge].parents.append(feature)
    repo.children[feature].add(merge)
    path, error = repo.path(feature, main)
    equal(error, None, "path error")
    equal(path, [feature, base, main], "equal-length paths choose smaller hash neighbor")


def run(args):
    source = args.source.resolve()
    report = {
        "kind": "local self-evaluation; not official Codyssey grading",
        "source": str(source),
        "provenance": ["Codyssey/mini-git/README.md", "Docs/codyssey/codyssey-orientation.md"],
        "stage": args.stage,
        "stretch": args.stretch,
        "results": [],
    }
    if not source.is_file():
        report["results"].append({"name": "source_load", "stage": 1, "basis": "harness", "status": "FAIL", "detail": f"source not found: {source}"})
    else:
        source_bytes = source.read_bytes()
        report["source_sha256"] = hashlib.sha256(source_bytes).hexdigest()
        with tempfile.TemporaryDirectory(prefix="mini-git-cts-") as temp:
            copy = Path(temp) / "main.py"
            shutil.copyfile(source, copy)
            ctx = {"copy": copy, "temp": temp}
            try:
                compile(source_bytes, str(source), "exec")
                spec = importlib.util.spec_from_file_location("_mini_git_cts_candidate", copy)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                try:
                    spec.loader.exec_module(module)
                finally:
                    sys.modules.pop(spec.name, None)
                ctx["module"] = module
                report["results"].append({"name": "source_load", "stage": 1, "basis": "harness", "status": "PASS", "detail": ""})
            except Exception as error:
                report["results"].append({"name": "source_load", "stage": 1, "basis": "harness", "status": "FAIL", "detail": f"{type(error).__name__}: {error}"})

            for name, stage, basis, optional, fn in CASES:
                if stage > args.stage or (optional and not args.stretch):
                    continue
                result = {"name": name, "stage": stage, "basis": basis, "optional": optional}
                if "module" not in ctx:
                    result.update(status="SKIP", detail="source_load failed")
                else:
                    try:
                        fn(ctx)
                        result.update(status="PASS", detail="")
                    except Exception as error:
                        result.update(status="FAIL", detail=f"{type(error).__name__}: {error}")
                report["results"].append(result)
    summary = {status: sum(item["status"] == status for item in report["results"]) for status in ("PASS", "FAIL", "SKIP")}
    report["summary"] = summary
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in report["results"]:
        print(f"{item['status']:4}  [{item['stage']}] {item['name']}" + (f": {item['detail']}" if item["detail"] else ""))
    print(f"\nPASS {summary['PASS']}  FAIL {summary['FAIL']}  SKIP {summary['SKIP']}")
    print(f"Report: {args.report.resolve()}")
    return 1 if summary["FAIL"] or summary["SKIP"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE / "main.py", help="candidate main.py (copied to a temporary directory)")
    parser.add_argument("--stage", type=int, choices=(1, 2, 3), default=3, help="run stages through this number")
    parser.add_argument("--stretch", action="store_true", help="also test synthetic multi-parent DAG tie")
    parser.add_argument("--report", type=Path, default=HERE / "cts-report.json", help="JSON result path")
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
