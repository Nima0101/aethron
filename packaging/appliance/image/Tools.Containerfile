FROM python:3.13.15-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
# Exact top-level packages; the complete resolved dpkg inventory is retained by
# prepare.py. Repository removal fails the build rather than silently upgrading.
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-arm=1:10.0.13+ds-0+deb13u1 \
    qemu-utils=1:10.0.13+ds-0+deb13u1 \
    e2fsprogs=1.47.2-3+b12 linux-image-cloud-arm64=6.12.111-1 \
    systemd-sysv=257.13-1~deb13u1 initramfs-tools=0.148.4 \
    && rm -rf /var/lib/apt/lists/*
