FROM python:latest AS base

RUN pip3 install requests pyyaml

WORKDIR /usr/src

COPY mailjet_state_reporter/__init__.py ./mailjet-state-reporter.py

ENTRYPOINT ["python"]

CMD ["mailjet-state-reporter.py"]
