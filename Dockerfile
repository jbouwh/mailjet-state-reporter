FROM alpine:3.24.4

ENV TZ=Europe/Amsterdam

# Install system dependencies and create non-root user.
# Paths are strictly separated:
#   /config  settings.yaml (read-only, owned by root; mount e.g. a ConfigMap)
#   /state   sync_state.json (the only persistent, writable state)
#   stdout   all log lines; set LOG_FILE to also write a log file
RUN apk upgrade \
    && apk add --update \
      ca-certificates tzdata curl tar build-base libpcap tcpdump python3 wget py3-pip py3-requests py3-yaml git \
      nano less libxml2 python3-dev libxslt-dev libxml2-dev bash openssl-dev libffi-dev \
    && ln -sf /usr/share/zoneinfo/$TZ /etc/localtime \
    && update-ca-certificates \
    && addgroup -S appgroup && adduser -S pythonrt -G appgroup -u 2001 \
    && mkdir -p /config /state /usr/src \
    && chown pythonrt:appgroup /state

USER pythonrt
# Never run from the config directory, so nothing gets written next to settings.yaml
WORKDIR /usr/src

ENV CONFIG_FILE=/config/settings.yaml \
    SYNC_STATE=/state/sync_state.json \
    LOG_FILE=

COPY mailjet_state_reporter/__init__.py /usr/src/mailjet-state-reporter.py

ENTRYPOINT ["python"]

CMD ["/usr/src/mailjet-state-reporter.py"]
