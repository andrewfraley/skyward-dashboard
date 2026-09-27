#!/bin/sh
# Every image the Dockerfile pulls must be digest-pinned and come from Docker Hub.
#
# Digest: a tag can be re-pointed at other contents, a digest can't.
# Docker Hub: Dependabot's 7-day cooldown needs the registry to report when an
# image was published. ghcr.io (and others) don't, so Dependabot would propose
# brand-new images there immediately. See DEVELOPING.md, "Supply chain".
#
#   scripts/check_base_images.sh [Dockerfile]      # CI runs this
set -eu
dockerfile="${1:-Dockerfile}"

# Stage names (FROM ... AS name) are references to earlier stages, not images.
stages=$(sed -nE 's/^FROM[[:space:]].*[[:space:]]AS[[:space:]]+([^[:space:]]+).*/\1/Ip' "$dockerfile" | tr 'A-Z' 'a-z')

# Image references: the argument of FROM (after any --flag=...) and of COPY --from=.
images=$(
    {
        sed -nE 's/^FROM[[:space:]]+(--[^[:space:]]+[[:space:]]+)*([^[:space:]]+).*/\2/Ip' "$dockerfile"
        grep -oiE -- '--from=[^[:space:]]+' "$dockerfile" | sed 's/^--from=//I'
    } | sort -u
)

status=0
for ref in $images; do
    lower=$(printf %s "$ref" | tr 'A-Z' 'a-z')
    if printf '%s\n' $stages | grep -qx -- "$lower"; then
        continue
    fi
    case "$ref" in
        *@sha256:*) ;;
        *) echo "::error file=$dockerfile::$ref is not pinned by digest (image:tag@sha256:...)"; status=1 ;;
    esac
    # A first path component with a dot or colon is a registry host.
    first=${ref%%/*}
    if [ "$first" != "$ref" ] && printf %s "$first" | grep -q '[.:]' && [ "$first" != docker.io ]; then
        echo "::error file=$dockerfile::$ref comes from $first; use Docker Hub, where Dependabot's cooldown works"
        status=1
    fi
done
[ "$status" = 0 ] && echo "check_base_images: every image is from Docker Hub and pinned by digest"
exit "$status"
