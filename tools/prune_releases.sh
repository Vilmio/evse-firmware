#!/usr/bin/env bash
# Ponecha jen poslednich KEEP tagu v* a jejich releasu, starsi smaze.
#
#   KEEP=3 DRY_RUN=1 tools/prune_releases.sh     # jen vypise, co by smazal
#
# - "Posledni" = nejvyssi verze podle nazvu tagu (sort -V), ne datum.
# - Release oznaceny jako Latest se NIKDY nemaze (stanice z nej stahuji
#   aktualizace), i kdyby ho predbehly novejsi pre-release tagy.
# - Release se maze i s tagem (--cleanup-tag); tag bez release zvlast.
# - Release, jehoz tag uz neexistuje (napr. draft), se smaze taky.
# - Resi jen tagy a releasy zacinajici "v"; nic jineho v repu nemaze.
#
# Vyzaduje GitHub CLI (gh) s GH_TOKEN a GH_REPO (v GitHub Actions nastaveno).
set -euo pipefail

KEEP="${KEEP:-3}"
DRY_RUN="${DRY_RUN:-0}"
REPO="${GH_REPO:?GH_REPO must be set (owner/repo)}"

run() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

latest=$(gh api "repos/$REPO/releases/latest" --jq .tag_name 2>/dev/null || true)
echo "Latest release: ${latest:-none} (always kept)"

# Chyba API musi beh zastavit (set -e): prazdny seznam tagu by jinak z kazdeho
# releasu udelal "release bez tagu" a smazal ho.
all_tags=$(gh api --paginate "repos/$REPO/tags" --jq '.[].name')
all_releases=$(gh api --paginate "repos/$REPO/releases" --jq '.[].tag_name')
tags=$(printf '%s\n' "$all_tags" | grep '^v' | sort -V -r || true)
releases=$(printf '%s\n' "$all_releases" | grep '^v' || true)
if [ -z "$tags" ] && [ -n "$releases" ]; then
  echo "No v* tags but releases exist - refusing to delete anything." >&2
  exit 1
fi

keep_list=$(printf '%s\n' "$tags" | head -n "$KEEP")
if [ -n "$latest" ]; then
  keep_list=$(printf '%s\n%s\n' "$keep_list" "$latest")
fi
echo "Keeping:"
printf '%s\n' "$keep_list" | sed '/^$/d' | sort -V -r -u | sed 's/^/  /'

is_kept() {
  printf '%s\n' "$keep_list" | grep -Fxq "$1"
}

deleted=0
for tag in $tags; do
  is_kept "$tag" && continue
  if printf '%s\n' "$releases" | grep -Fxq "$tag"; then
    echo "Deleting release and tag $tag"
    run gh release delete "$tag" --repo "$REPO" --yes --cleanup-tag
  else
    echo "Deleting tag $tag (no release)"
    run gh api -X DELETE "repos/$REPO/git/refs/tags/$tag"
  fi
  deleted=$((deleted + 1))
done

# releasy bez existujiciho tagu (drafty, rucne smazane tagy)
for tag in $releases; do
  is_kept "$tag" && continue
  printf '%s\n' "$tags" | grep -Fxq "$tag" && continue
  echo "Deleting release $tag (tag does not exist)"
  run gh release delete "$tag" --repo "$REPO" --yes
  deleted=$((deleted + 1))
done

echo "Done, $deleted item(s) $( [ "$DRY_RUN" = "1" ] && echo "would be " )deleted."
