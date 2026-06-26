# Bagheera backend — GPU image.
#
# Carries the FastAPI app PLUS the full ML stack, because the worker thread lazily
# imports torch/openslide/etc. at runtime and shells out to the baked-in TRIDENT and
# PANTHER repos (one shared venv at /opt/venv).
#
# Build context is the REPO ROOT (see docker-compose.yml), so paths below are repo-relative.
#
# Key build args (override in docker-compose.yml / .env once you know your hardware):
#   CUDA_IMAGE   - base image; MUST match the host driver (read `nvidia-smi`). Default 12.1.
#   TORCH_INDEX  - PyTorch wheel index matching CUDA_IMAGE (cu121 / cu118).
#   TRIDENT_REF  - git branch/tag to pin TRIDENT.
#   PANTHER_REF  - git branch/tag to pin PANTHER.

ARG CUDA_IMAGE=nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
FROM ${CUDA_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps: python, git/bash for the subprocess wrappers, openslide C lib for WSI
# decoding, libgl1/libglib2.0-0 for OpenCV (cv2).
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
        git bash build-essential curl ca-certificates \
        openslide-tools libopenslide0 \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Shared venv on PATH.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip wheel setuptools

# --- PyTorch (CUDA build) first, so the repos resolve against it ---------------------
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu121
RUN pip install torch torchvision --index-url ${TORCH_INDEX}

# --- Clone TRIDENT + PANTHER at pinned refs ------------------------------------------
ARG TRIDENT_REPO=https://github.com/mahmoodlab/TRIDENT.git
ARG TRIDENT_REF=main
ARG PANTHER_REPO=https://github.com/mahmoodlab/PANTHER.git
ARG PANTHER_REF=main
RUN git clone --depth 1 -b ${TRIDENT_REF} ${TRIDENT_REPO} /opt/TRIDENT \
 && git clone --depth 1 -b ${PANTHER_REF} ${PANTHER_REPO} /opt/PANTHER

# --- Install both repos' deps into the shared venv (best-effort across layouts) -------
# TRIDENT ships as a pip-installable package; PANTHER typically ships a requirements file.
# If a build fails here, it almost always means TRIDENT/PANTHER pin conflicting versions
# in one venv — see docs/docker.md for the fallback (separate env via TRIDENT_PYTHON).
RUN if [ -f /opt/TRIDENT/requirements.txt ]; then pip install -r /opt/TRIDENT/requirements.txt; fi \
 && if [ -f /opt/TRIDENT/pyproject.toml ] || [ -f /opt/TRIDENT/setup.py ]; then pip install -e /opt/TRIDENT; fi
RUN if [ -f /opt/PANTHER/requirements.txt ]; then pip install -r /opt/PANTHER/requirements.txt; fi \
 && if [ -f /opt/PANTHER/pyproject.toml ] || [ -f /opt/PANTHER/setup.py ]; then pip install -e /opt/PANTHER; fi

# --- Bagheera's own deps + the viz extras the worker imports lazily ------------------
COPY backend/requirements.txt /tmp/bagheera-requirements.txt
RUN pip install -r /tmp/bagheera-requirements.txt
RUN pip install \
        h5py scikit-learn umap-learn matplotlib \
        opencv-python-headless seaborn pandas openslide-python

# --- FAISS (GPU) for PANTHER's `--mode faiss` ----------------------------------------
# PANTHER calls faiss.Kmeans(..., gpu=numOfGPUs), so the CPU-only wheel won't do — it
# needs the CUDA build. Match the wheel to CUDA_IMAGE: faiss-gpu-cu12 for CUDA 12.x,
# faiss-gpu-cu11 for 11.x. (Override FAISS_PACKAGE if you change the CUDA base image.)
ARG FAISS_PACKAGE=faiss-gpu-cu12
RUN pip install ${FAISS_PACKAGE}

# --- App code ------------------------------------------------------------------------
COPY backend/ /app/backend/
RUN chmod +x /app/backend/scripts/*.sh
WORKDIR /app/backend

# Default in-container locations (paths overridable via .env / compose).
ENV TRIDENT_REPO_PATH=/opt/TRIDENT \
    PANTHER_REPO_PATH=/opt/PANTHER \
    TRIDENT_PYTHON=/opt/venv/bin/python

EXPOSE 8000
CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
