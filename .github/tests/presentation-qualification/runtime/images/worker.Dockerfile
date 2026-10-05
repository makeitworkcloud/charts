ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-venv ca-certificates \
      libreoffice-impress poppler-utils fonts-liberation fontconfig \
 && rm -rf /var/lib/apt/lists/*
COPY .github/tests/presentation-qualification/pins.env /tmp/pins.env
RUN set -a && . /tmp/pins.env && set +a \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir \
      jupyter-client=="$JUPYTER_CLIENT" ipykernel=="$IPYKERNEL" \
      pyzmq=="$PYZMQ" pycryptodomex=="$PYCRYPTODOMEX" \
 && rm /tmp/pins.env
COPY upstream-eg/etc/kernel-launchers /usr/local/bin/kernel-launchers
COPY upstream-eg/LICENSE.md /usr/local/bin/kernel-launchers/LICENSE.md
WORKDIR /opt/presentation
COPY .github/tests/presentation-qualification/runtime/images/worker_files/package.json /opt/presentation/package.json
RUN npm install --omit=dev && npm cache clean --force
COPY .github/tests/presentation-qualification/runtime/images/worker_files/build_deck.js \
     .github/tests/presentation-qualification/runtime/images/worker_files/build_task.py \
     .github/tests/presentation-qualification/runtime/images/worker_files/render_task.py /opt/presentation/
COPY .github/tests/presentation-qualification/lib/framing.py /opt/presentation/framing.py
