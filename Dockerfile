FROM kitware/trame:uv

ENV TRAME_PYTHON=3.14

RUN apt-get update \
    && apt-get install -y \
    libxrender1 libosmesa6 libgl1 libglx-mesa0 \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=trame-user:trame-user . /deploy

# entrypoint build runs setup/initialize.sh, then installs setup/requirements.txt
RUN /opt/trame/entrypoint.sh build

EXPOSE 80
