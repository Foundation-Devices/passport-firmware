commit_sha := `git rev-parse HEAD`

# build the firmware inside docker
docker-build:
  #!/usr/bin/env bash
  set -euxo pipefail
  docker build -t foundation-devices/firmware-builder:{{ commit_sha }} .
  docker run -it --rm -v "$PWD":/workspace \
    -w /workspace/ports/stm32 \
    --entrypoint bash \
    foundation-devices/firmware-builder:{{ commit_sha }} \
    -c 'make BOARD=Passport MPY_CROSS=/usr/bin/mpy-cross'

# run the built firmware through SHA256
sha: docker-build
  @shasum -a 256 ports/stm32/build-Passport/firmware.bin | awk '{print $1}'
