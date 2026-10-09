ARG TOOL_IMAGE
FROM ${TOOL_IMAGE} AS boot_tools
FROM ros@sha256:8f687fdf084482819aa7dab48c3887331edd0d3687b219951fdb66c418316ab1
# Exact Ubuntu userland; the separately inventoried Debian kernel/initrd mount it.
RUN apt-get update && apt-get install -y --no-install-recommends systemd-sysv=255.4-1ubuntu8.17 && rm -rf /var/lib/apt/lists/*
COPY --from=boot_tools /boot/ /boot/
COPY --from=boot_tools /usr/lib/modules/ /usr/lib/modules/
COPY requirements.lock /tmp/requirements.lock
COPY dependencies /tmp/dependencies
RUN printf '931c303696af6fa3417112103b1cad26890e5a07eccb5b99783700e33f2b8aad  /tmp/dependencies/pip-26.2-py3-none-any.whl\n' | sha256sum -c -
RUN python3 -m venv --system-site-packages --without-pip --copies /opt/aethron/venv && /opt/aethron/venv/bin/python -c 'import glob,runpy,sys; sys.path.insert(0,glob.glob("/tmp/dependencies/pip-*.whl")[0]); sys.argv=["pip","install","--no-index","--find-links","/tmp/dependencies","--require-hashes","-r","/tmp/requirements.lock"]; runpy.run_module("pip",run_name="__main__")' && rm -rf /tmp/dependencies /tmp/requirements.lock
COPY wheels /tmp/wheels
RUN /opt/aethron/venv/bin/python -m pip install --no-index --no-deps /tmp/wheels/*.whl && rm -rf /tmp/wheels
# Pip is a hash-verified build tool, not a runtime or offline-update dependency.
RUN /opt/aethron/venv/bin/python -m pip uninstall --yes pip
COPY provision_ros_sdk.py /tmp/provision.py
RUN /opt/aethron/venv/bin/python /tmp/provision.py && rm /tmp/provision.py
COPY appliance.json fixture.jsonl raw-depth.aeraw raw-depth.json ros-appliance.json ros-depth.json /opt/aethron/
COPY aethron.service /etc/systemd/system/aethron.service
COPY probe.service /etc/systemd/system/aethron-sil-probe.service
COPY ros-runtime.service /etc/systemd/system/aethron-ros-fixture.service
COPY ros-check.service /etc/systemd/system/aethron-ros-check.service
COPY boot_probe.py sensor_probe.py probe-profiles.json update_probe.py ros_fixture.py ros_lifecycle_probe.py ros_boot_probe.py ros-required /opt/aethron-sil/
COPY sign_bundle.py /tmp/sign.py
RUN useradd --system --home /nonexistent --shell /usr/sbin/nologin aethron && mkdir -p /etc/aethron /var/lib/aethron /var/lib/aethron-updates && chown root:aethron /var/lib/aethron-updates && chmod 0750 /var/lib/aethron-updates && chown aethron:aethron /var/lib/aethron && chmod 0700 /var/lib/aethron && systemctl enable aethron.service aethron-sil-probe.service aethron-ros-check.service && mkdir -p /etc/systemd/journald.conf.d && printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=8M\n' > /etc/systemd/journald.conf.d/aethron.conf
RUN --mount=type=secret,id=testkey /opt/aethron/venv/bin/python /tmp/sign.py && rm /tmp/sign.py
RUN mkdir -p /var/lib/aethron-sil && ln -sf /dev/null /etc/systemd/system/systemd-networkd.service && ln -sf /dev/null /etc/systemd/system/getty@tty1.service && ln -sf /dev/null /etc/systemd/system/serial-getty@ttyAMA0.service
RUN systemctl mask getty@.service serial-getty@.service console-getty.service getty-static.service lttng-sessiond.service apt-daily.timer apt-daily-upgrade.timer motd-news.timer
ENTRYPOINT []
CMD ["/sbin/init"]
