# Environment recipe for the EV3 armel cross-build. Base identity lives here only.
FROM ev3dev/debian-stretch-cross@sha256:819ea7442bbe109d2b39c6c7766e7d1fe635bb98b86c4f6c3b636c0ce176a29f

USER root

# Stretch is archived. Check signatures normally; disable only expired Release dates.
# Restrict package indexes to the host and EV3 architectures; do not upgrade GCC.
RUN printf '%s\n' \
      'deb [arch=amd64,armel] http://archive.debian.org/debian stretch main' \
      'deb [arch=amd64,armel] http://archive.debian.org/debian-security stretch/updates main' \
      > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
      libssl1.0-dev:armel=1.0.2u-1~deb9u7 \
      libavahi-client-dev:armel=0.6.32-2+deb9u1 \
      libavahi-common-dev:armel=0.6.32-2+deb9u1 \
    && test -f /usr/include/openssl/ssl.h \
    && test -f /usr/include/avahi-client/client.h \
    && test -f /usr/include/avahi-common/simple-watch.h \
    && rm -rf /var/lib/apt/lists/*

USER compiler

# Verify the compiler after installing dependencies. Expectations live here only.
RUN test "$(arm-linux-gnueabi-g++ --version | head -n 1)" = \
      'arm-linux-gnueabi-g++ (Debian 6.3.0-18) 6.3.0 20170516' \
    && printf '%s  %s\n' \
      '57d50f50faa7ac5a82d2ebe4066124e15249189a994cbd0f8d1da7a6d733e6b8' \
      "$(command -v arm-linux-gnueabi-g++)" | sha256sum --check --strict

WORKDIR /home/compiler
