export DOCKER_REGISTRY_BASE := ''

commit_sha := `git rev-parse HEAD`
docker_image := 'foundation-devices/firmware-builder:' + commit_sha
base_path := 'ports/stm32'
firmware_path := base_path + '/build-Passport/firmware.bin'

# build the docker image and then the firmware and bootloader
build: docker-build firmware-build bootloader-build

# build the dependency docker image
docker-build:
  #!/usr/bin/env bash
  set -exo pipefail
  docker build -t ${DOCKER_REGISTRY_BASE}{{ docker_image }} .

# build the firmware inside docker
firmware-build:
  #!/usr/bin/env bash
  set -exo pipefail
  docker run --rm -v "$PWD":/workspace \
    -w /workspace/{{ base_path }} \
    --entrypoint bash \
    ${DOCKER_REGISTRY_BASE}{{ docker_image }} \
    -c 'make BOARD=Passport MPY_CROSS=/usr/bin/mpy-cross'

# build the bootloader inside docker
bootloader-build:
  #!/usr/bin/env bash
  set -exo pipefail
  docker run --rm -v "$PWD":/workspace \
    -w /workspace/{{ base_path }} \
    --entrypoint bash \
    ${DOCKER_REGISTRY_BASE}{{ docker_image }} \
    -c 'make -C boards/Passport/bootloader'

# build the docker image and get the tools from it
tools: docker-build cosign-tool add-secrets-tool word-list-gen-tool

# get cosign tool from built docker image
cosign-tool:
  #!/usr/bin/env bash
  set -exo pipefail
  docker run --rm -v "$PWD":/workspace \
    -w /workspace \
    --entrypoint bash \
    ${DOCKER_REGISTRY_BASE}{{ docker_image }} \
    -c 'cp /usr/bin/cosign cosign'

# get add-secrets tool from built docker image
add-secrets-tool:
  #!/usr/bin/env bash
  set -exo pipefail
  docker run --rm -v "$PWD":/workspace \
    -w /workspace \
    --entrypoint bash \
    ${DOCKER_REGISTRY_BASE}{{ docker_image }} \
    -c 'make -C ports/stm32/boards/Passport/tools/add-secrets'

# get word_list_gen tool from built docker image
word-list-gen-tool:
  #!/usr/bin/env bash
  set -exo pipefail
  docker run --rm -v "$PWD":/workspace \
    -w /workspace/ports/stm32/boards/Passport/tools/word_list_gen \
    --entrypoint bash \
    ${DOCKER_REGISTRY_BASE}{{ docker_image }} \
    -c 'gcc word_list_gen.c bip39_words.c bytewords_words.c -o word_list_gen'

# run the built firmware through SHA256
verify-sha sha: build
  #!/usr/bin/env bash
  sha=$(shasum -a 256 {{ firmware_path }} | awk '{print $1}')

  echo -e "Expected SHA:\t{{ sha }}"
  echo -e "Actual SHA:\t${sha}"
  if [ "$sha" = "{{ sha }}" ]; then
    echo "Hashes match!"
  else
    echo "ERROR: Hashes DO NOT match!"
  fi

# sign the built firmware using a private key and the cosign tool
sign keypath version filepath=firmware_path: firmware-build
  #!/usr/bin/env bash
  set -exo pipefail

  docker run --rm -v "$PWD":/workspace \
    -w /workspace \
    --entrypoint bash \
    ${DOCKER_REGISTRY_BASE}{{ docker_image }} \
    -c "cosign -f {{ filepath }} -k {{ keypath }} -v {{ version }}"

# clean firmware build
clean:
  docker run --rm -v "$PWD":/workspace \
    -w /workspace/{{ base_path }} \
    --entrypoint bash \
    ${DOCKER_REGISTRY_BASE}{{ docker_image }} \
    -c "make clean BOARD=Passport"
