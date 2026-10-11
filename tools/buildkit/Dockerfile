# The images CI builds the published image with: never built, only read by
# .github/workflows/docker.yml, and here so Dependabot keeps their digests
# current with its cooldown. BuildKit runs the build and pushes the image;
# binfmt registers QEMU so the arm64 half can build on an amd64 runner.
FROM moby/buildkit:v0.33.1@sha256:cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea
FROM tonistiigi/binfmt:qemu-v10.2.3@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0
