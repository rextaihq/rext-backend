#!/usr/bin/env bash
# PreToolUse hook for Bash, Read, Edit, Write and Grep: keeps the contents of the env files (.env, .env.local,
# .env.dev, .env.stage, .envrc and every other .env name except *.example) out of the session. The Read deny
# rules in settings.json cover the usual names and the shell readers Claude Code recognises; this covers every
# name and any program (python -c, node -e, awk, a redirect, a substitution, a glob such as .e*, a brace expansion
# such as .env.{local,dev}), wherever a cd leads. On an env file a command may only test, list or count: test, [, ls,
# stat, wc (not --files0-from), and grep with -c, -q, -l or -L. For git and gh, only an env file given as a path counts
# (git diff --no-index, gh gist create); a commit message or a pull request body that mentions one does not. It reads
# the command as text, so it stops mistakes, not a program written to get round it. Exit 2 blocks the call; stderr is
# the reason Claude is shown.
#   Check: echo '{"tool_name":"Bash","tool_input":{"command":"cat .env"}}' | bash .claude/hooks/guard-env.sh; echo $?
input=$(cat)
# Quotes and backslashes are dropped first (.'e'nv is .env to the shell).
case "${input//[\'\"\\]/}" in *.e*|*'*'*|*'?'*|*'['*|*'.{'*|*'.,'*|*'.}'*|*glob*|*GLOBIGNORE*) ;; *) exit 0 ;; esac
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
import json, os, re, shlex, sys

REASON = os.environ["REASON"]
SEPARATORS = set(";&|()")
ENV_REF = re.compile(r"(?:^|[^\w.-])(\.env(?:rc)?(?:[.-][\w-]+)*)(?=$|[^\w.-])")
ALLOWED = {"test", "[", "[[", "ls", "stat", "wc"}
PATHS_ONLY = {"git", "gh"}
# Options whose value is text, not a path, for the subcommands that have them (--body-file and -F read a file, so
# they are not here; -b and -t mean something else to git, and to gh attestation -b is a file).
GIT_MESSAGE_COMMANDS = {("commit",), ("tag",), ("merge",), ("notes",), ("stash",)}
GIT_MESSAGE_OPTIONS = {"-m", "--message"}
GH_MESSAGE_COMMANDS = {("pr", "create"), ("pr", "edit"), ("pr", "comment"), ("pr", "review"), ("pr", "merge"),
                       ("pr", "revert"), ("pr", "close"), ("pr", "reopen"), ("issue", "create"), ("issue", "edit"),
                       ("issue", "comment"), ("issue", "close"), ("issue", "reopen"), ("release", "create"),
                       ("release", "edit"), ("discussion", "create"), ("discussion", "edit"),
                       ("discussion", "comment")}
GH_MESSAGE_OPTIONS = {"-b", "--body", "-t", "--title", "--subject", "-n", "--notes", "-c", "--comment"}
VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "-R", "--repo"}
# Set by a command that turns on a shell option letting a pattern reach a dot file without a leading dot or
# ignore case (shopt -s dotglob, nocaseglob or extglob; a GLOBIGNORE assignment), for the commands after it.
GLOB_OPTIONS = {"dotglob", "nocaseglob", "extglob"}
LOOSE = False
EXTGLOB = False
BRACE = re.compile(r"(?<!\$)\{([^{}]*)\}")

def command_words(words, count):
    # The first count words that are not options (git -C dir commit: commit), skipping the values of global options.
    found, i = [], 1
    while i < len(words) and len(found) < count:
        if words[i] in VALUE_OPTIONS:
            i += 2
            continue
        if not words[i].startswith("-"):
            found.append(words[i])
        i += 1
    return tuple(found)

def message_values(name, words):
    # The positions in words that hold a message, up to a "--" (after it everything is a path).
    if name == "git":
        options = GIT_MESSAGE_OPTIONS if command_words(words, 1) in GIT_MESSAGE_COMMANDS else set()
    else:
        options = GH_MESSAGE_OPTIONS if command_words(words, 2) in GH_MESSAGE_COMMANDS else set()
    found = set()
    for i, w in enumerate(words):
        if w == "--":
            break
        if w in options and i + 1 < len(words):
            found.add(i + 1)
        elif any(w.startswith(o + "=") if o.startswith("--") else len(w) > 2 and w.startswith(o) for o in options):
            found.add(i)
    return found

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

def brace_parts(inner):
    # The alternatives of one brace group, or None when it is not an expansion (the {} of find, a lone {x}). A number
    # range counts as its first number: digits spell no name.
    seq = re.fullmatch(r"(-?\d+|[A-Za-z])\.\.(-?\d+|[A-Za-z])(?:\.\.-?\d+)?", inner)
    if seq:
        a, b = seq.group(1), seq.group(2)
        if a.isalpha() and b.isalpha():
            lo, hi = sorted((ord(a), ord(b)))
            return [chr(c) for c in range(lo, hi + 1)]
        return None if a.isalpha() or b.isalpha() else [a]
    return inner.split(",") if "," in inner else None

def expanded(word):
    # The words brace expansion makes of word: .env.{local,dev} is .env.local and .env.dev. At most 1024.
    out, todo = [], [word]
    while todo and len(out) + len(todo) <= 1024:
        w = todo.pop()
        for m in BRACE.finditer(w):
            parts = brace_parts(m.group(1))
            if parts is not None:
                todo += [w[:m.start()] + p + w[m.end():] for p in parts]
                break
        else:
            out.append(w)
    return out + todo

def globbed(word):
    # A pattern the shell may expand to an env file, such as .e* or .[e]nv.secret, wherever the command runs. A
    # pattern reaches a dot file only from a literal leading dot, so it can reach an env file only when the text
    # before its first wildcard could begin ".env"; with dotglob or nocaseglob any start can.
    base = os.path.basename(word)
    cuts = [base.index(c) for c in "*?[" if c in base]
    if not cuts or base.endswith(".example"):
        return False
    lead = base[:min(cuts)]
    if LOOSE:
        lead = lead.lower()
    elif not lead.startswith("."):
        return False
    return ".env".startswith(lead) or lead.startswith(".env")

def touches(token):
    return any(refs(w) or globbed(w) for w in expanded(token))

def as_path(word):
    return not re.search(r"\s", word) or any(env_name(w) or globbed(w) for w in expanded(word))

def grep_counts_only(args):
    for a in args:
        if a in ("--count", "--quiet", "--silent", "--files-with-matches", "--files-without-match"):
            return True
        if a.startswith("-") and not a.startswith("--") and set(a[1:]) & set("cqlL"):
            return True
    return False

def note_options(segment):
    global LOOSE, EXTGLOB
    if segment and segment[0] == "shopt" and any(w.startswith("-") and "s" in w for w in segment[1:]):
        LOOSE = LOOSE or bool(GLOB_OPTIONS & set(segment))
        EXTGLOB = EXTGLOB or "extglob" in segment
    if any(re.fullmatch(r"GLOBIGNORE=.*", w) for w in segment):
        LOOSE = True

def check_segment(segment):
    note_options(segment)
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
        if any(i not in messages and touches(w) and as_path(w) for i, w in enumerate(words)):
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
if tool == "Bash":
    command = args.get("command") or ""
    try:
        check_command(command)
    except ValueError:
        if refs(command) and not re.match(r"\s*(test|\[)\s", command):
            block()
    # With extglob on, @(.e)nv and the like are patterns the word split would not see.
    if EXTGLOB and re.search(r"[?*+@!]\(", command):
        block()
elif tool in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"):
    if env_name(args.get("file_path") or args.get("notebook_path")):
        block()
elif tool == "Grep":
    if env_name(args.get("path")) or any(refs(" " + g) or globbed(g) for g in expanded(args.get("glob") or "")):
        block()
' <<< "$input"
