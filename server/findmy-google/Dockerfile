# Gegenstück für Google Find Hub (ehem. Find My Device) – EXPERIMENTELL.
#
# Basis: https://github.com/rolsch/google-find-hub-sync
#   (Fork von leonboe1/GoogleFindMyTools; enthält microservice.py + Dockerfile)
#
# Wichtig:
# - Die Erst-Authentifizierung braucht Google Chrome auf einem Desktop
#   (Windows) und erzeugt Auth/secrets.json. Diese Datei in das Volume
#   google-findmy-auth kopieren (siehe docs/findmy.md).
# - Die Registrierung eigener ESP32-Tracker erfolgt interaktiv über main.py
#   im selben Repo (ebenfalls in docs/findmy.md beschrieben).
#
# GIT_REF pinnen, sobald eine funktionierende Version verifiziert ist.

FROM python:3.12-slim

ARG GIT_REF=main

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 --branch "${GIT_REF}" https://github.com/rolsch/google-find-hub-sync.git . \
 && pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=5500

EXPOSE 5500

CMD ["python", "microservice.py"]
