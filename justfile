commit_sha := `git rev-parse HEAD`
base_path := 'ports/stm32'
firmware_path := base_path + '/build-Passport/firmware.bin'

# build the firmware inside docker
docker-build:
  #!/usr/bin/env bash
  set -euxo pipefail
  docker build -t foundation-devices/firmware-builder:{{ commit_sha }} .
  docker run -it --rm -v "$PWD":/workspace \
    -w /workspace/{{ base_path }} \
    --entrypoint bash \
    foundation-devices/firmware-builder:{{ commit_sha }} \
    -c 'make BOARD=Passport MPY_CROSS=/usr/bin/mpy-cross'

# run the built firmware through SHA256
verify-sha sha: docker-build
  echo "{{ sha }}  {{ firmware_path }}" | shasum -a 256 -c -

# sign the built firmware using a private key and the cosign tool
sign keypath version filepath=firmware_path: docker-build
  #!/usr/bin/env bash
  set -euxo pipefail

  docker run -it --rm -v "$PWD":/workspace \
    -w /workspace \
    --entrypoint bash \
    foundation-devices/firmware-builder:{{ commit_sha }} \
    -c "cosign -f {{ filepath }} -k {{ keypath }} -v {{ version }}"

# clean firmware build
clean:
  docker run -it --rm -v "$PWD":/workspace \
    -w /workspace/{{ base_path }} \
    --entrypoint bash \
    foundation-devices/firmware-builder:{{ commit_sha }} \
    -c "make clean BOARD=Passport"
