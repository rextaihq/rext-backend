#!/usr/bin/env bash
# PreToolUse hook for Bash: refuses a git push to main, staging or stage (from a session, merges into
# stage go through rext-control/scripts/app/merge.sh), a bare push whose configured target is one of them,
# a push of every branch at once (--all, --mirror, a wildcard refspec, push.default=matching, a mirror
# remote), git send-pack, and a forced push other than --force-with-lease (which a session needs after
# rebasing its own task branch). Exit 2 blocks the command; stderr is the reason Claude is shown.
# It reads the hook input (JSON) on stdin and parses the command itself, global options (-C, -c, --git-dir)
# and aliases included, rather than relying on the hook's "if" filter, which misses forms like `git -C . push`.
# It guards against mistakes, not against a program that runs git itself (python -c, a script).
#   Check: echo '{"tool_input":{"command":"git push origin main"},"cwd":"."}' | bash .claude/hooks/guard-push.sh; echo $?
input=$(cat)
case "$input" in *git*) ;; *) exit 0 ;; esac

if ! command -v python3 > /dev/null 2>&1; then
  # Without python3, a rougher check on the raw text, from each "git push" onwards. It can refuse a commit
  # message that quotes such a command; it does not read configuration or aliases.
  if grep -qE '(^|[^A-Za-z0-9_.-])git[^|&;]*[[:space:]]send-pack([[:space:]"]|$)' <<< "$input"; then
    echo "git send-pack is not used here: push your task branch with git push" >&2; exit 2
  fi
  gp='(^|[^A-Za-z0-9_.-])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push'
  if grep -qE "$gp"'[^|&;]*[[:space:]:+"'"'"'/\\](main|staging|stage)([[:space:]"'"'"'\\]|$)' <<< "$input"; then
    echo "a push to main, staging or stage is not allowed from a session: push your task branch and open a pull request into stage" >&2; exit 2
  fi
  if grep -qE "$gp"'[^|&;]*(\*|[[:space:]]--(al|mir|bran|pru)[a-z]*([[:space:]"=]|$))' <<< "$input"; then
    echo "a wildcard refspec or a push of every branch can update main or staging: push your task branch by name" >&2; exit 2
  fi
  if grep -qE "$gp"'[^|&;]*[[:space:]](--forc?e?([[:space:]"=]|$)|-[a-np-zA-Z]*f[a-zA-Z]*([[:space:]"]|$)|\+)' <<< "$input"; then
    echo "a forced push is refused: after rebasing your own task branch, use git push --force-with-lease" >&2; exit 2
  fi
  exit 0
fi

python3 -c '
import json, os, re, shlex, subprocess, sys

PROTECTED = {"main", "staging", "stage"}
SEPARATORS = set(";&|()")
EVERY_BRANCH = ("--mirror", "--all", "--branches", "--prune")
SAFE_FORCE = ("--force-with-lease", "--force-if-includes", "--no-force-with-lease", "--no-force-if-includes")

def block(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)

class Repo:
    # Where git runs and the global options it was given (-c, --git-dir, --work-tree), so configuration is
    # read the way the command itself would read it.
    def __init__(self, path, opts=()):
        self.path, self.opts = path, list(opts)
    def git(self, *args):
        try:
            r = subprocess.run(["git", "-C", self.path, *self.opts, *args], capture_output=True, text=True, timeout=5)
        except Exception:
            return ""
        return r.stdout.strip() if r.returncode == 0 else ""

def short(ref):
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref

def long_option(name, choices):
    # git accepts an unambiguous prefix of a long option (--mir for --mirror).
    for choice in choices:
        if name == choice or (len(name) >= 4 and choice.startswith(name)):
            return choice
    return None

def spec_target(spec, repo):
    # The branch a refspec writes to, and whether it forces.
    forced = spec.startswith("+")
    spec = spec[1:] if forced else spec
    if spec == ":":
        block("git push with \":\" pushes every matching branch: push your task branch by name")
    if "*" in spec:
        block("a wildcard refspec can update main or staging: push your task branch by name")
    src, _, dst = spec.partition(":")
    dst = dst or src
    if dst in ("HEAD", "@"):
        dst = repo.git("branch", "--show-current")
    return short(dst), forced

def bare_targets(repo, remote):
    # Where a push that names no branch goes: the remote, its push refspecs and mirror setting, and the
    # branch push.default chooses. These clones keep no tracking ref for a task branch, so read the config.
    current = repo.git("branch", "--show-current")
    if not remote:
        remote = (repo.git("config", f"branch.{current}.pushRemote") or repo.git("config", "remote.pushDefault")
                  or repo.git("config", f"branch.{current}.remote") or "origin")
    if repo.git("config", "--bool", f"remote.{remote}.mirror") == "true":
        block(f"the remote {remote} is configured as a mirror, so a push updates every branch: push your task branch by name")
    mode = repo.git("config", "push.default") or "simple"
    if mode == "matching":
        block("this checkout pushes every matching branch when no branch is named (push.default=matching): "
              "push your task branch by name")
    targets, forced = [], False
    for value in repo.git("config", "--get-all", f"remote.{remote}.push").splitlines():
        dst, spec_forced = spec_target(value, repo)
        targets.append(dst)
        forced = forced or spec_forced
    if mode in ("upstream", "tracking"):
        merge = repo.git("config", f"branch.{current}.merge")
        if merge:
            targets.append(short(merge))
    full = repo.git("rev-parse", "--symbolic-full-name", "@{push}")
    if full.startswith("refs/remotes/") and full.count("/") >= 3:
        targets.append(full.split("/", 3)[3])
    targets.append(current)
    return targets, forced

def check_push(args, repo):
    takes_value = ("--push-option", "--receive-pack", "--exec")
    forced = False
    repo_arg = None
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1:]
            break
        if a.startswith("--"):
            name, eq, value = a.partition("=")
            if name in SAFE_FORCE:
                pass
            elif long_option(name, ("--repo",)):
                if eq:
                    repo_arg = value
                else:
                    repo_arg = args[i + 1] if i + 1 < len(args) else ""
                    i += 1
            elif long_option(name, takes_value):
                if not eq:
                    i += 1
            elif long_option(name, EVERY_BRANCH):
                block(f"git push {long_option(name, EVERY_BRANCH)} can update main or staging: push your task branch by name")
            elif long_option(name, ("--force",)) and not name.startswith("--force-"):
                forced = True
        elif a.startswith("-o"):
            if a == "-o":
                i += 1  # -o VALUE; an attached -oVALUE is one word
        elif a.startswith("-") and len(a) > 1:
            if "f" in a[1:]:
                forced = True
        else:
            positional.append(a)
        i += 1
    # With --repo every positional argument is a refspec; without it the first one is the repository.
    if repo_arg is not None:
        remote, refspecs = repo_arg, positional
    else:
        remote, refspecs = (positional[0] if positional else None), positional[1:]
    targets = []
    if not refspecs:
        targets, forced_by_config = bare_targets(repo, remote)
        forced = forced or forced_by_config
    for spec in refspecs:
        dst, spec_forced = spec_target(spec, repo)
        targets.append(dst)
        forced = forced or spec_forced
    for dst in targets:
        if dst in PROTECTED:
            block(f"a push to {dst} is not allowed from a session: push your task branch (app/<task>-<slug>) "
                  "and open a pull request into stage; rext-control/scripts/app/merge.sh does the merge")
    if forced:
        block("a forced push is refused: after rebasing your own task branch, use git push --force-with-lease; "
              "never force a branch someone else works on")

def dispatch(sub, rest, repo, depth=0):
    if sub == "push":
        check_push(rest, repo)
    elif sub == "send-pack":
        block("git send-pack is not used here: push your task branch with git push")
    elif depth < 5:
        alias = repo.git("config", f"alias.{sub}")
        if alias.startswith("!"):
            if re.search(r"\b(push|send-pack)\b", alias):
                block(f"the git alias {sub} runs a push: use git push itself, so the guard can read it")
        elif alias:
            words = shlex.split(alias)
            if words:
                dispatch(words[0], words[1:] + rest, repo, depth + 1)

def check_git(args, path):
    opts = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            path = os.path.join(path, os.path.expanduser(args[i + 1]))
            i += 2
        elif a == "-c" and i + 1 < len(args):
            opts += ["-c", args[i + 1]]
            i += 2
        elif a in ("--git-dir", "--work-tree", "--namespace") and i + 1 < len(args):
            opts.append(f"{a}={args[i + 1]}")
            i += 2
        elif a.startswith(("--git-dir=", "--work-tree=", "--namespace=")):
            opts.append(a)
            i += 1
        elif a == "--config-env":
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            break
    if i < len(args):
        dispatch(args[i], args[i + 1:], Repo(path, opts))

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
if not re.search(r"\bgit\b", command):
    sys.exit(0)
try:
    check_command(command, cwd)
except ValueError:
    # Unbalanced quotes: fall back to the plain text.
    if re.search(r"\bsend-pack\b", command):
        block("git send-pack is not used here: push your task branch with git push")
    if re.search(r"push[^|&;]*[\s:+\"\x27](main|staging|stage)([\s\"\x27]|$)", command):
        block("a push to main, staging or stage is not allowed from a session")
    if re.search(r"push[^|&;]*\s(--force(\s|=|$)|-[a-np-zA-Z]*f[a-zA-Z]*(\s|$)|\+)", command):
        block("a forced push is refused: use git push --force-with-lease on your own task branch")
' <<< "$input"
