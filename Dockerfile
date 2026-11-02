FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV OILAGENT_CORE_ROOT=/app
COPY requirements.lock pyproject.toml ./
RUN torch_arch="$(uname -m)" && pip install --no-cache-dir --timeout 60 \
    "https://download.pytorch.org/whl/cpu/torch-2.15.0%2Bcpu-cp313-cp313-manylinux_2_28_${torch_arch}.whl"
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
COPY config ./config
COPY data ./data
COPY scripts ./scripts
RUN pip install --no-cache-dir --no-build-isolation --no-deps . \
    && useradd --create-home --uid 10001 analyst \
    && mkdir -p /app/workspace/runtime && chown -R analyst:analyst /app/workspace
USER analyst
ENTRYPOINT ["python", "-m", "analyst.mcp_server"]
