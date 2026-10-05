#!/usr/bin/env bash
# PreToolUse hook for Bash: refuses a git push to main, staging or stage (from a session, merges into
# stage go through rext-control/scripts/app/merge.sh), a bare push from a checkout of one of them, a
# push of every branch at once (--all, --mirror, a wildcard refspec, push.default=matching), and a forced push other than --force-with-lease (which a session needs
# after rebasing its own task branch). Exit 2 blocks the command; stderr is the reason Claude is shown.
# It reads the hook input (JSON) on stdin and parses the command itself rather than relying on the
# hook's "if" filter, which misses forms like `git -C . push`.
#   Check: echo '{"tool_input":{"command":"git push origin main"},"cwd":"."}' | bash .claude/hooks/guard-push.sh; echo $?
input=$(cat)
case "$input" in *push*) ;; *) exit 0 ;; esac

if ! command -v python3 > /dev/null 2>&1; then
  # Without python3, a rougher check on the raw text.
  if grep -qE 'push[^|&;]*[[:space:]:+"](main|staging|stage)([[:space:]"]|$)' <<< "$input"; then
    echo "a push to main, staging or stage is not allowed from a session: push your task branch and open a pull request into stage" >&2; exit 2
  fi
  if grep -qE 'push[^|&;]*\*' <<< "$input"; then
    echo "a wildcard refspec can update main or staging: push your task branch by name" >&2; exit 2
  fi
  if grep -qE 'push[^|&;]*[[:space:]](--force([[:space:]"=]|$)|-[a-zA-Z]*f[a-zA-Z]*([[:space:]"]|$)|\+)' <<< "$input"; then
    echo "a forced push is refused: after rebasing your own task branch, use git push --force-with-lease" >&2; exit 2
  fi
  exit 0
fi

python3 -c '
import json, os, re, shlex, subprocess, sys

PROTECTED = {"main", "staging", "stage"}
SEPARATORS = set(";&|()")

def block(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)

def git_out(path, *args):
    try:
        r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""

def short(ref):
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref

def bare_push_target(path):
    # Where a push with no refspec goes: the push destination of the current branch, else its name.
    full = git_out(path, "rev-parse", "--symbolic-full-name", "@{push}")
    if full.startswith("refs/remotes/") and full.count("/") >= 3:
        return full.split("/", 3)[3]
    return git_out(path, "branch", "--show-current")

def check_push(args, path):
    takes_value = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
    forced = False
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1:]
            break
        if a in takes_value:
            i += 2
            continue
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            if name == "--force":
                forced = True
            elif name in ("--mirror", "--all", "--branches", "--prune"):
                block(f"git push {name} can update main or staging: push your task branch by name")
        elif a.startswith("-") and len(a) > 1:
            if "f" in a[1:]:
                forced = True
        else:
            positional.append(a)
        i += 1
    refspecs = positional[1:]
    targets = []
    if not refspecs:
        # A push that names no branch follows the configuration, which can select every matching branch.
        configured = git_out(path, "config", "--get-regexp", r"^remote\..*\.push$")
        if git_out(path, "config", "push.default") == "matching" or "*" in configured or re.search(r"\s\+?:$", configured, re.M):
            block("this checkout pushes every matching branch when no branch is named (push.default or a remote push refspec): "
                  "push your task branch by name")
        targets.append(bare_push_target(path))
    for spec in refspecs:
        if spec.startswith("+"):
            forced = True
            spec = spec[1:]
        if spec == ":":
            block("git push with \":\" pushes every matching branch: push your task branch by name")
        if "*" in spec:
            block("a wildcard refspec can update main or staging: push your task branch by name")
        src, _, dst = spec.partition(":")
        dst = dst or src
        if dst in ("HEAD", "@"):
            dst = git_out(path, "branch", "--show-current")
        targets.append(short(dst))
    for dst in targets:
        if dst in PROTECTED:
            block(f"a push to {dst} is not allowed from a session: push your task branch (app/<task>-<slug>) "
                  "and open a pull request into stage; rext-control/scripts/app/merge.sh does the merge")
    if forced:
        block("a forced push is refused: after rebasing your own task branch, use git push --force-with-lease; "
              "never force a branch someone else works on")

def check_git(args, path):
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            path = os.path.join(path, os.path.expanduser(args[i + 1]))
            i += 2
        elif a in ("-c", "--git-dir", "--work-tree", "--namespace", "--config-env"):
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            break
    if i < len(args) and args[i] == "push":
        check_push(args[i + 1:], path)

def check_command(text, path):
    lexer = shlex.shlex(text.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    segment = []
    for tok in list(lexer) + [";"]:
        if tok and set(tok) <= SEPARATORS:
            if segment and segment[0] == "cd" and len(segment) > 1:
                path = os.path.join(path, os.path.expanduser(segment[1]))
            for j, word in enumerate(segment):
                name = os.path.basename(word)
                if name == "git":
                    check_git(segment[j + 1:], path)
                elif name in ("bash", "sh", "zsh", "dash") and segment[j + 1:j + 2] == ["-c"] and j + 2 < len(segment):
                    check_command(segment[j + 2], path)
                elif name == "eval":
                    check_command(" ".join(segment[j + 1:]), path)
            segment = []
        else:
            segment.append(tok)

data = json.loads(sys.stdin.read() or "{}")
command = (data.get("tool_input") or {}).get("command") or ""
cwd = data.get("cwd") or os.getcwd()
if not re.search(r"\bpush\b", command):
    sys.exit(0)
try:
    check_command(command, cwd)
except ValueError:
    # Unbalanced quotes: fall back to the plain text.
    if re.search(r"push[^|&;]*[\s:+\"\x27](main|staging|stage)([\s\"\x27]|$)", command):
        block("a push to main, staging or stage is not allowed from a session")
    if re.search(r"push[^|&;]*\s(--force(\s|=|$)|-[a-zA-Z]*f[a-zA-Z]*(\s|$)|\+)", command):
        block("a forced push is refused: use git push --force-with-lease on your own task branch")
' <<< "$input"
