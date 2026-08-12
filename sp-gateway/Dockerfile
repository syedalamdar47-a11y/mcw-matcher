# SimplePractice gateway — read-only, PHI-minimising.
#
# Base image ships Chromium plus every system library it needs, pinned to the
# same Playwright version as requirements.txt. Version skew between the client
# library and the bundled browser is the single most common cause of a headless
# job that works locally and dies in the container.
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Playwright browsers are already baked into this image.
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    # Session state lives on the mounted volume, encrypted.
    SP_STATE_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY check_login.py ./
COPY discover_calendar.py ./
COPY discover_calendar2.py ./
COPY discover_calendar3.py ./
COPY discover_calendar4.py ./
COPY discover_calendar5.py ./
COPY discover_calendar6.py ./
COPY discover_calendar7.py ./
COPY verify_no_conflicts.py ./

# --- Filesystem posture -------------------------------------------------------
# The container runs as a non-root user that owns nothing except /data. Chromium
# is additionally launched with its disk cache disabled (see src/session.py), so
# fetched page bodies stay in memory. Both belong together: the flags stop the
# browser writing, and the permissions stop it writing anywhere useful if a flag
# is ever dropped.
RUN useradd --create-home --uid 10001 gateway \
    && mkdir -p /data \
    && chown -R gateway:gateway /app /data
USER gateway

# Chromium is unhappy with the default 64MB /dev/shm. fly.toml does not expose a
# shm size knob, so src/session.py passes --disable-dev-shm-usage instead, which
# redirects shared memory to /tmp. Keep both in mind if tabs start crashing.

# No EXPOSE and no public service: the authenticated worker must not be
# reachable from the internet. See fly.toml.
ENTRYPOINT ["python", "-m", "src"]
CMD ["--serve"]
