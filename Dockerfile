FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV OILAGENT_CORE_ROOT=/app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
RUN pip install --no-cache-dir --no-build-isolation --no-deps . \
    && useradd --create-home --uid 10001 analyst \
    && mkdir -p /app/workspace/runtime && chown -R analyst:analyst /app/workspace
USER analyst
ENTRYPOINT ["python", "-m", "analyst.mcp_server"]
