FROM alpine:3.23.3

ENV TZ=Europe/Amsterdam

# Install system dependencies and create non-root user
RUN apk upgrade \
    && apk add --update \
      ca-certificates tzdata curl tar build-base libpcap tcpdump python3 wget py3-pip git \
      nano less libxml2 python3-dev libxslt-dev libxml2-dev bash openssl-dev libffi-dev \
    && ln -sf /usr/share/zoneinfo/$TZ /etc/localtime \
    && update-ca-certificates \
    && addgroup -S appgroup && adduser -S leanpython -G appgroup \
    && mkdir -p /app \
    && chown -R leanpython:appgroup /app

USER python_runtime
WORKDIR /usr/src

# Install uv and create venv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && /home/python_runtime/.local/bin/uv venv

ENV VIRTUAL_ENV=/home/python_runtime/.venv
ENV PATH="/home/python_runtime/.local/bin:/home/python_runtime/.venv/bin:$PATH"

RUN uv --version

COPY mailjet_state_reporter/__init__.py ./mailjet-state-reporter.py

ENTRYPOINT ["python"]

CMD ["mailjet-state-reporter.py"]
