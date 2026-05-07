FROM kitware/trame

ENV TRAME_PYTHON=3.13

RUN apt-get update \
    && apt-get install -y \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Copy your app and setup files
COPY --chown=trame-user:trame-user . /deploy

# Build: initialize.sh runs first (exports requirements.txt), then installs it
RUN /opt/trame/entrypoint.sh build

EXPOSE 80