#!/usr/bin/env bash
# Archive of the Manager's code for a review, without its secrets.
#
#   ./tools/export-for-review.sh [output directory]      (default: /tmp)
#
# What is left out, and why:
#   - .env and every .env.* but .env.example: the passwords and keys;
#   - keys and certificates (*.pem, *.key, *.crt, *.p12, *.pfx, id_rsa*,
#     id_ed25519*, acme.json, .htpasswd);
#   - data: database dumps and their .counts, *.sql.gz, logs;
#   - archives, editor and patch leftovers (*.zip, *.tar*, *.tgz, *.bak,
#     *.orig, *.rej, *.swp, *~);
#   - caches and environments (.git, __pycache__, .pytest_cache, .ruff_cache,
#     .mypy_cache, node_modules, venv, .venv);
#   - any file over 2 MB: nothing in the code is that large.
# The names of the files left out go in REVIEW-EXPORT.txt, inside the archive:
# a name tells the reviewer a file exists, never what it holds.
#
# Then the kept files are searched, and the archive is not written if one of
# them holds:
#   - the value of a secret of .env (a key whose name says PASS, SECRET, TOKEN,
#     KEY, SALT, PRIVATE or CREDENTIAL), unless .env.example ships that same
#     value for the key: that one is public. The values are read, compared and
#     never printed: a hit names the file and the key, not the value;
#   - a private key block or a GitHub, AWS or Slack token.
# A user:password@ in a URL is shown as a warning (docs write it with a
# ${VARIABLE}), and so are the lab's addresses and the domain names outside
# tests, to make generic before the code is published.
#
# Exit status: 0 archive written, 1 a secret was found (nothing written),
# 2 a file could not be read (run it with sudo).
set -euo pipefail
cd "$(dirname "$0")/.."
root=$PWD
outDir=${1:-/tmp}
name="manager-review-$(date +%Y%m%d-%H%M)"
work=$(mktemp -d)
chmod 700 "$work"
trap 'rm -rf "$work"' EXIT

# ---- 1. What goes in, what stays out -------------------------------------
excludedWhy() {  # $1 = path relative to the root; prints the reason, or nothing
    local base=${1##*/}
    case "$base" in
        .env.example) return ;;
        .env|.env.*) echo "secrets"; return ;;
        *.pem|*.key|*.crt|*.p12|*.pfx|*.jks|id_rsa*|id_ed25519*|id_ecdsa*|acme.json|.htpasswd|htpasswd)
            echo "key or certificate"; return ;;
        *.dump|*.dump.counts|*.counts|*.sql.gz|*.log) echo "data"; return ;;
        *.zip|*.tar|*.tar.gz|*.tgz|*.gz|*.bak|*.orig|*.rej|*.swp|*~|*.pyc)
            echo "archive or leftover"; return ;;
    esac
    local size
    size=$(stat -c %s "$1" 2>/dev/null || echo 0)
    if [ "$size" -gt 2097152 ]; then echo "over 2 MB"; fi
}

: > "$work/kept"; : > "$work/left"; : > "$work/unreadable"
while IFS= read -r -d '' f; do
    f=${f#./}
    why=$(excludedWhy "$f")
    if [ -n "$why" ]; then
        printf '%s\t%s\n' "$f" "$why" >> "$work/left"
    elif [ ! -r "$f" ]; then
        echo "$f" >> "$work/unreadable"
    else
        echo "$f" >> "$work/kept"
    fi
done < <(find . \( -name .git -o -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \
                  -o -name .mypy_cache -o -name node_modules -o -name venv -o -name .venv \) -prune \
             -o \( -type f -o -type l \) -print0 | sort -z)

if [ -s "$work/unreadable" ]; then
    echo "Unreadable by $(id -un), run it again with sudo:"
    sed 's/^/  /' "$work/unreadable"
    exit 2
fi

# ---- 2. Secrets in what goes in ------------------------------------------
found=0
: > "$work/values"
exampleValue() {  # the value .env.example gives a key, quotes removed; empty if none
    [ -r "$root/.env.example" ] || return 0
    local v
    v=$(sed -n "s/^\(export \)\{0,1\}$1=//p" "$root/.env.example" | tail -n 1)
    v=${v%$'\r'}; v=${v#\"}; v=${v%\"}; v=${v#\'}; v=${v%\'}
    printf '%s' "$v"
}
for envFile in $(grep -E '(^|/)\.env(\..*)?'$'\t' "$work/left" | cut -f1 | grep -v '\.env\.example$' || true); do
    if [ ! -r "$envFile" ]; then
        echo "WARNING: $envFile is not readable: its values were not compared (sudo checks them)."
        continue
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        key=${line%%=*}; key=${key#export }; key=${key// /}
        value=${line#*=}
        value=${value#\"}; value=${value%\"}; value=${value#\'}; value=${value%\'}
        echo "$key" | grep -qiE 'PASS|SECRET|TOKEN|KEY|SALT|PRIVATE|CREDENTIAL' || continue
        [ ${#value} -ge 6 ] || continue
        # The value .env.example ships for the same key is public by
        # definition (the repository's .env starts as a copy of it): only a
        # value the deployment changed is a secret.
        [ "$value" = "$(exampleValue "$key")" ] && continue
        printf '%s\t%s\n' "$key" "$value" >> "$work/values"
    done < "$envFile"
done
while IFS=$'\t' read -r key value; do
    hits=$(tr '\n' '\0' < "$work/kept" | xargs -0 grep -lF -- "$value" 2>/dev/null || true)
    for h in $hits; do
        echo "SECRET: $h holds the value of $key"
        found=1
    done
done < "$work/values"
rm -f "$work/values"

patterns=(
    'private key|-----BEGIN [A-Z ]*PRIVATE KEY-----'
    'GitHub token|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}'
    'AWS key|AKIA[0-9A-Z]{16}'
    'Slack token|xox[baprs]-[A-Za-z0-9-]{10,}'
)
for p in "${patterns[@]}"; do
    label=${p%%|*}; re=${p#*|}
    # file:line only: the line itself could be the secret.
    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        echo "SECRET: $hit ($label)"
        found=1
    done < <(tr '\n' '\0' < "$work/kept" | xargs -0 grep -nEo -- "$re" 2>/dev/null | cut -d: -f1,2 | sort -u || true)
done

if [ "$found" -ne 0 ]; then
    echo
    echo "Nothing written: remove the secrets above from these files, then run it again."
    exit 1
fi

warn() {  # $1 label, $2 regex, $3 path pattern to skip (optional); one line per file
    local hits
    hits=$(grep -vE -- "${3:-^$}" "$work/kept" | tr '\n' '\0' \
           | xargs -0 grep -cE -- "$2" 2>/dev/null | grep -v ':0$' || true)
    if [ -n "$hits" ]; then
        echo "WARNING, $1 (to read, not blocking; file:lines):"
        echo "$hits" | sed 's/^/  /'
    fi
}
warn "user:password@ in a URL" '://[^/:@[:space:]$]+:[^/@[:space:]$]{3,}@'
# Tests use private addresses on purpose: only the rest is listed.
warn "private addresses outside tests/, to make generic before publishing" \
     '\b(172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}|10\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3})\.[0-9]{1,3}\b' '^tests/'

# Domain names, outside tests: a lab or a customer name in a comment or an
# example is what the address check above does not see. The usual neutral
# ones are left out (example.*, github.com, w3.org, apache.org).
domains=$(grep -v '^tests/' "$work/kept" | tr '\n' '\0' \
          | xargs -0 grep -IoiE '\b[a-z0-9-]+(\.[a-z0-9-]+)*\.(fr|com|org|net|eu|io)\b' 2>/dev/null \
          | grep -viE ':([a-z0-9-]+\.)*(example\.(org|com|net|fr)|github\.com|w3\.org|apache\.org)$' \
          | sort | uniq -c | awk '{print "  " $2 " (" $1 ")"}' || true)
if [ -n "$domains" ]; then
    echo "WARNING, domain names outside tests/, to check before publishing (file:domain):"
    echo "$domains"
fi

# ---- 3. The archive ------------------------------------------------------
{
    echo "Export for review: $name, from $root, by $(id -un) on ${HOSTNAME:-$(uname -n)}"
    echo "$(wc -l < "$work/kept") files kept. Left out (name, reason):"
    sed 's/^/  /' "$work/left"
} > "$work/REVIEW-EXPORT.txt"

mkdir -p "$outDir"
dest="$outDir/$name.tar.gz"
tar -czf "$dest" --transform "s,^,$name/," -T "$work/kept" -C "$work" REVIEW-EXPORT.txt

echo
echo "Left out: $(wc -l < "$work/left") files (list in REVIEW-EXPORT.txt, inside the archive)"
echo "Archive:  $dest"
echo "Files:    $(tar -tzf "$dest" | grep -vc '/$')"
echo "Size:     $(du -h "$dest" | cut -f1)"
echo "md5:      $(md5sum "$dest" | cut -d' ' -f1)"
