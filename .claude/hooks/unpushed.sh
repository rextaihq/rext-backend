#!/usr/bin/env bash
# SessionEnd hook: says so when the current branch holds commits the remote does not have. It asks the remote,
# because a clone that fetches only the base branches keeps no remote-tracking ref for a task branch.
cd "${CLAUDE_PROJECT_DIR:-.}" 2> /dev/null || exit 0
branch=$(git branch --show-current 2> /dev/null)
[ -n "$branch" ] || exit 0
remote=$(timeout 10 git ls-remote origin "refs/heads/$branch" 2> /dev/null | cut -f1)
if [ -z "$remote" ]; then
  n=$(git log --oneline HEAD --not --remotes 2> /dev/null | wc -l)
  [ "$n" -gt 0 ] && echo "warning: $branch has never been pushed ($n commit(s) on no remote branch)"
elif [ "$remote" != "$(git rev-parse HEAD)" ]; then
  if git merge-base --is-ancestor "$remote" HEAD 2> /dev/null; then
    echo "warning: $(git rev-list --count "$remote..HEAD") commit(s) on $branch are not pushed"
  else
    echo "warning: $branch differs from origin/$branch (rebased, or someone else pushed): look before you push"
  fi
fi
exit 0
