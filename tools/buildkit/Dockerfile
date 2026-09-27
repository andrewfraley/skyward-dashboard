# The images CI builds the published image with: never built, only read by
# .github/workflows/docker.yml, and here so Dependabot keeps their digests
# current with its cooldown. BuildKit runs the build and pushes the image;
# binfmt registers QEMU so the arm64 half can build on an amd64 runner.
FROM moby/buildkit:v0.32.2@sha256:28a898719c18a33f4e8000685287fa36fd0dd9560c6440227d3a732d79bb41d8
FROM tonistiigi/binfmt:qemu-v10.2.3@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0
