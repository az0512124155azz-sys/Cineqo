#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT_DIR/open_source/manifest.json"
LOCKFILE="$ROOT_DIR/open_source/LOCK.json"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/third_party"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

lock_tmp="$(mktemp)"
printf '{\n  "schema_version": 1,\n  "generated_at": "%s",\n  "components": [\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$lock_tmp"

first=1
mapfile -t components < <(jq -c '.components[] | select(.include_in_import == true)' "$MANIFEST")

for component in "${components[@]}"; do
  id="$(jq -r '.id' <<<"$component")"
  upstream="$(jq -r '.upstream' <<<"$component")"
  ref="$(jq -r '.ref' <<<"$component")"
  destination="$(jq -r '.destination' <<<"$component")"
  declared_license="$(jq -r '.license' <<<"$component")"

  echo "==> Importing $id from $upstream ($ref)"
  checkout="$TMP_ROOT/$id"

  git clone --filter=blob:none --no-checkout "$upstream" "$checkout"
  git -C "$checkout" checkout "$ref"
  resolved_sha="$(git -C "$checkout" rev-parse HEAD)"

  # Defensive checks: source imports must retain an upstream license file.
  license_file=""
  for candidate in LICENSE LICENSE.txt LICENSE.md COPYING COPYING.txt; do
    if [[ -f "$checkout/$candidate" ]]; then
      license_file="$candidate"
      break
    fi
  done

  if [[ -z "$license_file" ]]; then
    echo "ERROR: $id has no recognized top-level license file; refusing import." >&2
    exit 1
  fi

  target="$ROOT_DIR/$destination"
  rm -rf "$target"
  mkdir -p "$(dirname "$target")"

  # Copy working tree only. Never vendor the upstream .git directory.
  rsync -a --delete --exclude='.git' "$checkout/" "$target/"

  cat > "$target/CINEQO_UPSTREAM.json" <<EOF
{
  "id": "$id",
  "upstream": "$upstream",
  "requested_ref": "$ref",
  "resolved_commit": "$resolved_sha",
  "declared_license": "$declared_license",
  "license_file": "$license_file"
}
EOF

  if [[ $first -eq 0 ]]; then
    printf ',\n' >> "$lock_tmp"
  fi
  first=0

  jq -n \
    --arg id "$id" \
    --arg upstream "$upstream" \
    --arg requested_ref "$ref" \
    --arg resolved_commit "$resolved_sha" \
    --arg declared_license "$declared_license" \
    --arg destination "$destination" \
    '{id:$id,upstream:$upstream,requested_ref:$requested_ref,resolved_commit:$resolved_commit,declared_license:$declared_license,destination:$destination}' \
    >> "$lock_tmp"
done

printf '\n  ]\n}\n' >> "$lock_tmp"
mv "$lock_tmp" "$LOCKFILE"

echo "Open-source source import complete."
echo "Pinned revisions written to open_source/LOCK.json"
