ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG WORKER_IMAGE=__PPTX_QUAL_WORKER_IMAGE__
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY .github/tests/presentation-qualification/pins.env /tmp/pins.env
RUN set -a && . /tmp/pins.env && set +a \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir \
      jupyter-enterprise-gateway=="$ENTERPRISE_GATEWAY" jupyter-client=="$JUPYTER_CLIENT" \
      pyzmq=="$PYZMQ" kubernetes=="$KUBERNETES_PY" jinja2=="$JINJA2" pyyaml=="$PYYAML" \
      requests=="$REQUESTS" websocket-client=="$WEBSOCKET_CLIENT" Pillow=="$PILLOW" \
 && rm /tmp/pins.env
COPY upstream-eg/etc/kernel-launchers /usr/local/bin/kernel-launchers
COPY upstream-eg/LICENSE.md /usr/local/bin/kernel-launchers/LICENSE.md
COPY upstream-eg/etc/kernelspecs/python_kubernetes /usr/local/share/jupyter/kernels/presentation
COPY upstream-eg/LICENSE.md /usr/local/share/jupyter/kernels/presentation/LICENSE.md
COPY .github/tests/presentation-qualification/runtime/k8s/kernel-pod.yaml.j2 /usr/local/bin/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2
RUN sed -i "s|__PPTX_QUAL_WORKER_IMAGE__|${WORKER_IMAGE}|" /usr/local/bin/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2 \
 && ! grep -q __PPTX_QUAL_WORKER_IMAGE__ /usr/local/bin/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2
COPY .github/tests/presentation-qualification/runtime/images/gateway_files/kernelspec_patch.py /tmp/kernelspec_patch.py
RUN /opt/venv/bin/python /tmp/kernelspec_patch.py \
      --kernelspec /usr/local/share/jupyter/kernels/presentation \
      --launcher /usr/local/bin/kernel-launchers/kubernetes/scripts/launch_kubernetes.py \
      --interpreter /opt/venv/bin/python \
      --worker-image "${WORKER_IMAGE}"
COPY .github/tests/presentation-qualification/runtime/images/gateway_files/render_check.py /tmp/render_check.py
RUN /opt/venv/bin/python /tmp/render_check.py \
      --template /usr/local/bin/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2 \
      --worker-image "${WORKER_IMAGE}"
COPY .github/tests/presentation-qualification/runtime/client /opt/qual/client
COPY .github/tests/presentation-qualification/lib /opt/qual/lib
COPY .github/tests/presentation-qualification/runtime/images/gateway_files/startup_capture.py /opt/qual/startup_capture.py
ENV PATH=/opt/venv/bin:${PATH}
