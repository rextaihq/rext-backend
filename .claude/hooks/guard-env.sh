#!/usr/bin/env bash
# PreToolUse hook for Bash, Read, Edit, Write and Grep: keeps the contents of the env files (.env, .env.local,
# .env.dev, .env.stage, .envrc and every other .env name except *.example) out of the session. The Read deny
# rules in settings.json cover the usual names and the shell readers Claude Code recognises; this covers every
# name and any program (python -c, node -e, awk, a redirect, a substitution, a glob such as .e*). On an env file a
# command may only test, list or count: test, [, ls, stat, wc (not --files0-from), and grep with -c, -q, -l or -L.
# For git and gh, only an env file given as a path counts (git diff --no-index, gh gist create); a commit message or
# a pull request body that mentions one does not. Exit 2 blocks the call; stderr is the reason Claude is shown.
#   Check: echo '{"tool_name":"Bash","tool_input":{"command":"cat .env"}}' | bash .claude/hooks/guard-env.sh; echo $?
input=$(cat)
case "$input" in *.env*|*.e*|*'*'*|*'?'*|*'['*) ;; *) exit 0 ;; esac
reason="an env file holds secrets and is not read in a session: check one with test -s .env or grep -c NAME .env; .env.example lists the names"

if ! command -v python3 > /dev/null 2>&1; then
  # Without python3, a rougher check on the raw text: an env name other than *.example next to a reading tool.
  if grep -qE '"file_path":[[:space:]]*"[^"]*/?\.env(rc)?([.-][A-Za-z0-9_.-]+)?"' <<< "$input" && ! grep -qE '"file_path":[[:space:]]*"[^"]*\.example"' <<< "$input"; then
    echo "$reason" >&2; exit 2
  fi
  if grep -qE '(^|[^A-Za-z0-9_-])(cat|head|tail|sed|awk|less|more|python3?|node|perl|ruby|source|xxd|od|strings|base64|cut|sort|jq|cp)[[:space:]]([^|;&]*[^A-Za-z0-9_.-])?\.env(rc)?([.-][A-Za-z0-9_-]+)*([^A-Za-z0-9_.-]|$)' <<< "$input" \
     && ! grep -qE '\.env(\.[A-Za-z0-9_-]+)*\.example' <<< "$input"; then
    echo "$reason" >&2; exit 2
  fi
  exit 0
fi

REASON="$reason" python3 -c '
import fnmatch, glob, json, os, re, shlex, sys

REASON = os.environ["REASON"]
SEPARATORS = set(";&|()")
ENV_REF = re.compile(r"(?:^|[^\w.-])(\.env(?:rc)?(?:[.-][\w-]+)*)(?=$|[^\w.-])")
ALLOWED = {"test", "[", "[[", "ls", "stat", "wc"}
PATHS_ONLY = {"git", "gh"}
# Options whose value is text, not a path, for the subcommands that have them (--body-file and -F read a file, so
# they are not here; -b and -t mean something else to git).
GIT_MESSAGE_COMMANDS = {"commit", "tag", "merge", "notes", "stash"}
GIT_MESSAGE_OPTIONS = {"-m", "--message"}
GH_MESSAGE_OPTIONS = {"-b", "--body", "-t", "--title", "-n", "--notes"}

def message_values(name, words):
    # The positions in words that hold a message, up to a "--" (after it everything is a path).
    if name == "git":
        sub = None
        i = 1
        while i < len(words):
            w = words[i]
            if w in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"):
                i += 2
            elif w.startswith("-"):
                i += 1
            else:
                sub = w
                break
        options = GIT_MESSAGE_OPTIONS if sub in GIT_MESSAGE_COMMANDS else set()
    else:
        options = GH_MESSAGE_OPTIONS
    found = set()
    for i, w in enumerate(words):
        if w == "--":
            break
        if w in options and i + 1 < len(words):
            found.add(i + 1)
        elif any(w.startswith(o + "=") for o in options if o.startswith("--")):
            found.add(i)
        elif name == "git" and "-m" in options and re.fullmatch(r"-m.+", w):
            found.add(i)
    return found
# Names a glob is tried against: the usual env files.
LIKELY = [".env", ".env.local", ".env.development", ".env.production", ".env.test", ".env.dev", ".env.stage", ".envrc",
          ".env.backup", ".env.bak"]

def block():
    print(REASON, file=sys.stderr)
    sys.exit(2)

def secret(name):
    return not name.endswith(".example")

def env_name(path):
    base = os.path.basename(path or "")
    return re.fullmatch(r"\.env(rc)?([.-].+)?", base) is not None and secret(base)

def refs(text):
    return [m.group(1) for m in ENV_REF.finditer(text) if secret(m.group(1))]

CWD = "."

def globbed(token):
    # A pattern the shell may expand to an env file, such as .e* or .[e]nv.secret: tried against the usual
    # names and against the files it matches where the command runs.
    base = os.path.basename(token)
    if not any(c in base for c in "*?["):
        return False
    if any(fnmatch.fnmatchcase(name, base) for name in LIKELY):
        return True
    try:
        return any(env_name(found) for found in glob.glob(os.path.join(CWD, token)))
    except Exception:
        return True

def touches(token):
    return bool(refs(token)) or globbed(token)

def grep_counts_only(args):
    for a in args:
        if a in ("--count", "--quiet", "--silent", "--files-with-matches", "--files-without-match"):
            return True
        if a.startswith("-") and not a.startswith("--") and set(a[1:]) & set("cqlL"):
            return True
    return False

def check_segment(segment):
    hits = [t for t in segment if touches(t)]
    if not hits:
        return
    # A substitution prints whatever it reads, whichever command it is handed to.
    if any(("$(" in t or "`" in t or "<(" in t) for t in hits):
        block()
    words = [t for t in segment if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t)]
    while words and words[0] in ("sudo", "command", "env", "time", "nice", "nohup", "exec"):
        words = words[1:]
    name = os.path.basename(words[0]) if words else ""
    if name in PATHS_ONLY:
        # A path names the file itself (HEAD:.env, some dir/.env.local); the value of a message option only mentions one.
        messages = message_values(name, words)
        if any(i not in messages and touches(w) and (not re.search(r"\s", w) or env_name(w) or globbed(w))
               for i, w in enumerate(words)):
            block()
        return
    if name == "wc" and any(t.startswith("--files0-from") for t in words[1:]):
        block()
    if name in ALLOWED:
        return
    if name in ("grep", "egrep", "fgrep", "rg") and grep_counts_only(words[1:]):
        return
    block()

def check_command(text):
    lexer = shlex.shlex(text.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    segment = []
    for tok in list(lexer) + [";"]:
        if tok and set(tok) <= SEPARATORS:
            check_segment(segment)
            segment = []
        else:
            segment.append(tok)

data = json.loads(sys.stdin.read() or "{}")
tool = data.get("tool_name") or ""
args = data.get("tool_input") or {}
CWD = data.get("cwd") or os.getcwd()
if tool == "Bash":
    command = args.get("command") or ""
    try:
        check_command(command)
    except ValueError:
        if refs(command) and not re.match(r"\s*(test|\[)\s", command):
            block()
elif tool in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"):
    if env_name(args.get("file_path") or args.get("notebook_path")):
        block()
elif tool == "Grep":
    if env_name(args.get("path")) or refs(" " + (args.get("glob") or "")):
        block()
' <<< "$input"
