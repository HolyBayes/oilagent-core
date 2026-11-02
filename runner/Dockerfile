FROM python:3.13-slim
COPY runner/requirements.lock /runner/requirements.lock
RUN pip install --no-cache-dir -r /runner/requirements.lock
COPY runner/worker.py /runner/worker.py
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["python", "-I", "/runner/worker.py"]
