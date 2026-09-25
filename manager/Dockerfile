# Manager — reproducible image.
# Dependencies are installed at build time from pinned versions and the base
# image is pinned by digest, so two builds of the same commit run the same
# bytes — without the digest they would not. To move the pin, deliberately:
#   docker pull python:3.12-slim, then copy the digest it prints below, and
#   run the tests on the new image before deploying it.
# For development, docker-compose.yml mounts the source over /app so edits
# are live.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Nothing here needs root: the process reads its sources and talks to two
# network services. Running as a user keeps a future flaw in the application
# from being a flaw with root on the container.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && adduser --system --group --no-create-home app
COPY --chown=app:app . .
USER app

EXPOSE 8200
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
