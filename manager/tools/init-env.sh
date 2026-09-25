#!/bin/sh
# Fill in the secrets of the Manager's .env, once, after a clone.
#
#   ./tools/init-env.sh [file]          (default: .env)
#
# The repository ships .env with the defaults and every secret empty, so that
# a deployment starts from a working file (as the gateway's .env does). This
# script only fills what is still empty, never overwrites a value:
#   - MANAGER_SESSION_SECRET and INGEST_TOKEN: generated;
#   - the password of DATABASE_URL, while it is CHANGE_ME: generated;
#   - PROXYAPI_ADMIN_TOKEN: not generated, it must be the proxyAPI's own
#     PROXY_ADMIN_TOKEN; reported when empty.
# A second run changes nothing. No secret is printed: the commands that need
# one read it from the file.
#
# Inside a git checkout the file is then marked skip-worktree: a filled .env
# never shows in git status and cannot be committed by accident.
#
# Exit status: 0 done, 1 the file is missing or unreadable.
set -eu
cd "$(dirname "$0")/.."
file=${1:-.env}
[ -f "$file" ] || { echo "$file: not found (run from a checkout of the repository)" >&2; exit 1; }

# 32 random bytes, hex: safe in sed, in a URL and in an HTTP header.
random() { od -An -N"${1:-32}" -tx1 /dev/urandom | tr -d ' \n'; }
value() { sed -n "s/^$1=//p" "$file" | tail -n 1; }

umask 077
tmp=$(mktemp "$file.XXXXXX")
trap 'rm -f "$tmp"' EXIT
cp "$file" "$tmp"
changed=""

fill() {  # name, generated value: only when the line is present and empty
    if grep -q "^$1=$" "$tmp"; then
        sed -i "s/^$1=$/$1=$2/" "$tmp"
        changed="$changed $1"
    fi
}
fill MANAGER_SESSION_SECRET "$(random 32)"
fill INGEST_TOKEN "$(random 24)"
if grep -q '^DATABASE_URL=.*:CHANGE_ME@' "$tmp"; then
    sed -i "s/^\(DATABASE_URL=[^:]*:\/\/[^:]*:\)CHANGE_ME@/\1$(random 16)@/" "$tmp"
    changed="$changed DATABASE_URL"
fi

cat "$tmp" > "$file"
chmod 600 "$file"

if [ -n "$changed" ]; then
    echo "Generated:$changed"
else
    echo "Nothing to generate: every secret already has a value."
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
   && git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
    git update-index --skip-worktree "$file"
    echo "$file marked skip-worktree: its values stay out of git status and commits."
fi

[ -n "$(value PROXYAPI_ADMIN_TOKEN)" ] || \
    echo "To do: PROXYAPI_ADMIN_TOKEN is empty; copy PROXY_ADMIN_TOKEN from the proxyAPI's .env (supervision stays empty until then)."

cat <<'EOF'

Next steps (each command reads the secret from the file, nothing to copy by hand):
  1. database role, with the password just written in DATABASE_URL:
       sed "s/CHANGE_ME/$(sed -n 's#^DATABASE_URL=[^:]*://[^:]*:\([^@]*\)@.*#\1#p' .env)/" db/bootstrap.sql \
         | docker exec -i postgres psql -v ON_ERROR_STOP=1 -U root -d postgres
  2. gateways: LOG_PUSH_TOKEN = the INGEST_TOKEN of this file
       grep '^INGEST_TOKEN=' .env
  3. first sign-in: account admin, password MANAGER_DEFAULT_PASSWORD, to change at once.
EOF
