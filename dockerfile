FROM ubuntu:24.04
ARG BUILD_VERSION
ENV BUILD_VERSION=$BUILD_VERSION

# Team convention: WORKDIR passed from docker-compose
ARG WORKDIR
ARG USERNAME=ubuntu
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# sudo support (team convention)
RUN apt-get update \
&& apt-get install -y sudo \
&& echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
&& chmod 0440 /etc/sudoers.d/$USERNAME

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    iputils-ping \
    vim \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── uv setup (team convention, pinned version from team dockerfile) ──
# OLD (team template): COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
# Store Python + venv inside the project folder so named volumes cache them
ENV UV_PYTHON_INSTALL_DIR=${WORKDIR}/.python
ENV UV_CACHE_DIR=${WORKDIR}/.uv_cache

ENV PATH="/home/${USERNAME}/.local/bin:$PATH"
ENV PATH="${WORKDIR}/.venv/bin:$PATH"

# src/ layout: tell Python where to find the policy_checker package
ENV PYTHONPATH="${WORKDIR}/src"

# [Optional] Set the default user (team convention)
USER $USERNAME
WORKDIR ${WORKDIR}

# ── Dev container mode (team convention) ────────────────────────────────
# Project is mounted as a volume at runtime.
# Dependencies are installed by `uv sync` after container starts —
# this keeps the image small and lets .venv be cached in a named volume.
#
# To install dependencies after container starts:
#   uv sync
#
# To run the web dashboard:
#   uv run uvicorn policy_checker.web.app:app --host=0.0.0.0 --port=8000
#
# To run the pipeline:
#   uv run python -m policy_checker.langgraph_agent.run --source ait

# Create all cache directories with correct ownership BEFORE switching user
RUN mkdir -p /Projects/compliance-checker/.uv_cache \
    && mkdir -p /Projects/compliance-checker/.venv \
    && mkdir -p /Projects/compliance-checker/.python \
    && chown -R ubuntu:ubuntu /Projects/compliance-checker

# Switch to ubuntu user permanently
USER ubuntu

# Now everything created after this is owned by ubuntu, not root

EXPOSE 8000
ENTRYPOINT []
CMD ["sleep", "infinity"]