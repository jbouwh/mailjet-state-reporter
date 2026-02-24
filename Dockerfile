FROM alpine:3.23.3

ENV TZ=Europe/Amsterdam

# Install system dependencies and create non-root user
RUN apk upgrade \
    && apk add --update \
      ca-certificates tzdata curl tar build-base libpcap tcpdump python3 wget py3-pip py3-requests py3-yaml git \
      nano less libxml2 python3-dev libxslt-dev libxml2-dev bash openssl-dev libffi-dev \
    && ln -sf /usr/share/zoneinfo/$TZ /etc/localtime \
    && update-ca-certificates \
    && addgroup -S appgroup && adduser -S pythonrt -G appgroup -u 2001 \
    && mkdir -p /config \
    && chown -R pythonrt:appgroup /config \
    && mkdir -p /usr/src \
    && chown -R pythonrt:appgroup /usr/src

USER pythonrt
WORKDIR /config

COPY mailjet_state_reporter/__init__.py /usr/src/mailjet-state-reporter.py

ENTRYPOINT ["python"]

CMD ["/usr/src/mailjet-state-reporter.py"]
