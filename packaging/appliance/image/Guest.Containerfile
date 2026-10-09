ARG TOOL_IMAGE
FROM ${TOOL_IMAGE}
COPY requirements.lock /tmp/requirements.lock
RUN python -m venv --copies /opt/aethron/venv && /opt/aethron/venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
COPY wheels /tmp/wheels
RUN /opt/aethron/venv/bin/pip install --no-index --find-links /tmp/wheels aethron-edge==0.1.0 && rm -rf /tmp/wheels /tmp/requirements.lock
COPY appliance.json fixture.jsonl raw-depth.aeraw raw-depth.json /opt/aethron/
COPY aethron.service /etc/systemd/system/aethron.service
COPY probe.service /etc/systemd/system/aethron-sil-probe.service
COPY boot_probe.py ros_boot_probe.py sensor_probe.py probe-profiles.json update_probe.py /opt/aethron-sil/
COPY sign_bundle.py /tmp/sign.py
RUN useradd --system --home /nonexistent --shell /usr/sbin/nologin aethron && mkdir -p /etc/aethron /var/lib/aethron /var/lib/aethron-updates && chown root:aethron /var/lib/aethron-updates && chmod 0750 /var/lib/aethron-updates && chown aethron:aethron /var/lib/aethron && chmod 0700 /var/lib/aethron && systemctl enable aethron.service aethron-sil-probe.service && mkdir -p /etc/systemd/journald.conf.d && printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=8M\n' > /etc/systemd/journald.conf.d/aethron.conf
RUN --mount=type=secret,id=testkey python /tmp/sign.py && rm /tmp/sign.py
RUN mkdir -p /var/lib/aethron-sil && ln -sf /dev/null /etc/systemd/system/systemd-networkd.service && ln -sf /dev/null /etc/systemd/system/getty@tty1.service && ln -sf /dev/null /etc/systemd/system/serial-getty@ttyAMA0.service
