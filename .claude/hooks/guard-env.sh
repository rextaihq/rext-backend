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
import fnmatch, json, os, re, shlex, sys

REASON = os.environ["REASON"]
SEPARATORS = set(";&|()")
ENV_REF = re.compile(r"(?:^|[^\w.-])(\.env(?:rc)?(?:[.-][\w-]+)*)(?=$|[^\w.-])")
ALLOWED = {"test", "[", "[[", "ls", "stat", "wc"}
PATHS_ONLY = {"git", "gh"}
# Options whose value is text, not a path, for the subcommands that have them (--body-file and -F read a file, so
# they are not here; -b and -t mean something else to git, and to gh attestation -b is a file).
GIT_MESSAGE_COMMANDS = {("commit",), ("tag",), ("merge",), ("notes",), ("stash",)}
GIT_MESSAGE_OPTIONS = {"-m", "--message"}
# git bundles short options (commit -am "x"); the first one in a bundle that takes a value ends it (-Fm reads m).
GIT_SHORT_WITH_VALUE = set("cCFtSu")
BODY, TITLE, COMMENT = {"-b", "--body"}, {"-t", "--title"}, {"-c", "--comment"}
NOTES = {"-n", "--notes"}
GH_MESSAGE_OPTIONS = {("pr", "create"): BODY | TITLE, ("pr", "edit"): BODY | TITLE, ("pr", "comment"): BODY,
                      ("pr", "review"): BODY,  # its -c is a switch
                      ("pr", "merge"): BODY | {"-t", "--subject"}, ("pr", "revert"): BODY | TITLE,
                      ("pr", "close"): COMMENT, ("pr", "reopen"): COMMENT, ("issue", "create"): BODY | TITLE,
                      ("issue", "edit"): BODY | TITLE, ("issue", "comment"): BODY, ("issue", "close"): COMMENT,
                      ("issue", "reopen"): COMMENT, ("release", "create"): NOTES | TITLE,
                      ("release", "edit"): NOTES | TITLE, ("discussion", "create"): BODY | TITLE,
                      ("discussion", "edit"): BODY | TITLE, ("discussion", "comment"): BODY}
VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "-R", "--repo"}
WRAPPERS = ("sudo", "command", "builtin", "env", "time", "nice", "nohup", "exec")
# The shell options that let a pattern reach a dot file without a leading dot or ignore case, once any command
# so far has set one (shopt -s; a GLOBIGNORE with a value turns dotglob on). Nothing turns one off again here: a
# later shopt -u or unset may sit in a branch that does not run (shopt -s dotglob || shopt -u dotglob).
GLOB_OPTIONS = {"dotglob", "nocaseglob", "extglob"}
SHELL_OPTIONS = set()
LOOSE = False
EXTGLOB = False
# A wildcard in quotes or after a backslash is not the shell one: the program it is handed to reads the pattern
# (find -name "*"), with no leading-dot rule. It goes through the word split as one of these.
QUOTED = {"*": "\ue000", "?": "\ue001", "[": "\ue002"}
UNQUOTE = str.maketrans({v: k for k, v in QUOTED.items()})
# The names a program owned pattern that starts with a wildcard is tried against (one that starts with a dot is
# checked against every env name: env_pattern).
LIKELY = [".env", ".env.local", ".env.development", ".env.production", ".env.test", ".env.dev", ".env.stage",
          ".env.staging", ".env.prod", ".envrc", ".env.backup", ".env.bak", ".env.old", ".env.secret",
          ".env.neon-backup"]
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
        options = GH_MESSAGE_OPTIONS.get(command_words(words, 2), set())
    found = set()
    for i, w in enumerate(words):
        if w == "--":
            break
        if w in options and i + 1 < len(words):
            found.add(i + 1)
        elif any(w.startswith(o + "=") for o in options if o.startswith("--")):
            found.add(i)
        elif options and re.fullmatch(r"-[A-Za-z].*", w):
            # A bundle of short options (-am, -bTEXT): the message sits in it or in the next word.
            for j, ch in enumerate(w[1:], 1):
                if "-" + ch in options:
                    found.add(i if j < len(w) - 1 else i + 1)
                    break
                if not ch.isalpha() or (name == "git" and ch in GIT_SHORT_WITH_VALUE) or name == "gh":
                    break
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

def mark_quoted(text):
    # The command with each quoted or escaped wildcard replaced by its QUOTED stand-in.
    out, quote, i = [], None, 0
    while i < len(text):
        c = text[i]
        if c == "\\" and quote != "\x27" and i + 1 < len(text):
            out += [c, QUOTED.get(text[i + 1], text[i + 1])]
            i += 2
            continue
        if quote and c == quote:
            quote = None
        elif quote:
            c = QUOTED.get(c, c)
        elif c in "\x27\"":
            quote = c
        out.append(c)
        i += 1
    return "".join(out)

def globbed(word):
    # A pattern that may reach an env file. One the shell expands (cat .e*, .[e]nv.secret) reaches a dot file
    # only from a literal leading dot, so it counts when the text before its first wildcard could begin ".env"
    # (any start can with dotglob or nocaseglob), wherever the command runs. One in quotes is for the program
    # (find -name "*"), which has no such rule: it counts when it matches one of the usual env names.
    if word.startswith("-") and "=" in word:
        word = word.split("=", 1)[1]  # --include=*.py
    base = os.path.basename(word)
    if base.translate(UNQUOTE).endswith(".example"):
        return False
    cuts = [base.index(c) for c in "*?[" if c in base]
    if cuts:
        lead = base[:min(cuts)].translate(UNQUOTE)
        if LOOSE:
            lead = lead.lower()
        elif not lead.startswith("."):
            return False
        return ".env".startswith(lead) or lead.startswith(".env")
    if any(c in base for c in QUOTED.values()):
        pattern = base.translate(UNQUOTE)
        if pattern.startswith("."):
            return env_pattern(pattern)
        return any(fnmatch.fnmatchcase(name, pattern) for name in LIKELY)
    return False

def pattern_items(pattern):
    # A pattern as a list of items: a set of characters (one character), or None for *.
    items, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            items.append(None)
        elif c == "?":
            items.append(set(map(chr, range(32, 127))))
        elif c == "[" and "]" in pattern[i + 2:]:
            end = pattern.index("]", i + 2)
            body, negate = pattern[i + 1:end], pattern[i + 1:i + 2] in ("!", "^")
            body = body[1:] if negate else body
            chars = set()
            for m in re.finditer(r"(.)-(.)|(.)", body):
                chars |= set(map(chr, range(ord(m.group(1)), ord(m.group(2)) + 1))) if m.group(1) else {m.group(3)}
            items.append(set(map(chr, range(32, 127))) - chars if negate else chars)
            i = end
        else:
            items.append({c})
        i += 1
    return items

def env_pattern(pattern):
    # Whether a pattern (fnmatch rules, no leading-dot rule) can match a name that begins with .env: every
    # env name does. It walks the pattern over ".env"; what is left of the pattern can always match the rest.
    items = pattern_items(pattern)
    def closure(states):
        out = set(states)
        for k in sorted(states):
            while k < len(items) and items[k] is None:
                k += 1
                out.add(k)
        return out
    states = closure({0})
    for ch in ".env":
        states = closure({k + 1 for k in states if k < len(items) and items[k] is not None and ch in items[k]}
                         | {k for k in states if k < len(items) and items[k] is None})
        if not states:
            return False
    return True

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

def command_of(segment):
    # The command a segment runs: without its variable assignments and wrappers (sudo, command, env ...).
    words = [t for t in segment if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t)]
    while words and words[0] in WRAPPERS:
        words = words[1:]
    return words

def note_options(segment):
    global LOOSE, EXTGLOB
    words = command_of(segment)
    if words[:1] == ["shopt"]:
        flags = "".join(w[1:] for w in words[1:] if w.startswith("-"))
        if "s" in flags:
            SHELL_OPTIONS.update(GLOB_OPTIONS & set(words))
    for w in segment:
        if w.startswith("GLOBIGNORE=") and w != "GLOBIGNORE=":
            SHELL_OPTIONS.add("dotglob")
    LOOSE = bool(SHELL_OPTIONS)
    EXTGLOB = "extglob" in SHELL_OPTIONS

def check_segment(segment):
    note_options(segment)
    hits = [t for t in segment if touches(t)]
    if not hits:
        return
    # A substitution prints whatever it reads, whichever command it is handed to.
    if any(("$(" in t or "`" in t or "<(" in t) for t in hits):
        block()
    words = command_of(segment)
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
    lexer = shlex.shlex(mark_quoted(text).replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
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
    # The glob is for ripgrep, not the shell: every wildcard in it is the program kind.
    glob = (args.get("glob") or "").translate(str.maketrans(QUOTED))
    if env_name(args.get("path")) or any(refs(" " + g) or globbed(g) for g in expanded(glob)):
        block()
' <<< "$input"
