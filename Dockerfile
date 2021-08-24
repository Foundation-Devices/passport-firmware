FROM ubuntu:18.04 AS cross_build
RUN apt-get update && \
    apt-get install -y git make gcc-arm-none-eabi python3 gcc && \
    rm -rf /var/lib/apt/lists/*
COPY drivers /workspace/passport-firmware/drivers
COPY docs /workspace/passport-firmware/docs
COPY extmod /workspace/passport-firmware/extmod
COPY lib /workspace/passport-firmware/lib
COPY mpy-cross /workspace/passport-firmware/mpy-cross
COPY py /workspace/passport-firmware/py
WORKDIR /workspace/passport-firmware/mpy-cross
RUN make

FROM ubuntu:18.04 AS cosign_build
WORKDIR /workspace
RUN apt-get update && \
    apt-get install -y git make libssl-dev gcc && \
    rm -rf /var/lib/apt/lists/*
COPY ports/stm32/boards/Passport/tools/cosign /workspace/passport-firmware/ports/stm32/boards/Passport/tools/cosign
COPY ports/stm32/boards/Passport/include /workspace/passport-firmware/ports/stm32/boards/Passport/include
COPY lib /workspace/passport-firmware/lib
COPY ports/stm32/boards/Passport/common /workspace/passport-firmware/ports/stm32/boards/Passport/common
WORKDIR /workspace/passport-firmware/ports/stm32/boards/Passport/tools/cosign
RUN make

FROM ubuntu:18.04 AS firmware_builder
COPY --from=cosign_build \
    /workspace/passport-firmware/ports/stm32/boards/Passport/tools/cosign/x86/release/cosign /usr/bin/cosign
COPY --from=cross_build \
    /workspace/passport-firmware/mpy-cross/mpy-cross /usr/bin/mpy-cross
RUN apt-get update && \
    apt-get install -y make gcc-arm-none-eabi autotools-dev automake libtool python3 && \
    rm -rf /var/lib/apt/lists/*
