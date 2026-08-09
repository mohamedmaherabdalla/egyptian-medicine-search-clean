FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2

RUN useradd --create-home --uid 1000 medicine
WORKDIR /home/medicine/service

COPY app/requirements-api.txt /tmp/requirements-api.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements-api.txt

COPY --chown=medicine:medicine app ./app
COPY --chown=medicine:medicine \
    benchmark_01_legacy/evaluate_current_app_search.py \
    ./benchmark_01_legacy/evaluate_current_app_search.py
COPY --chown=medicine:medicine \
    benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py \
    ./benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py
COPY --chown=medicine:medicine \
    benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py \
    benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py \
    benchmark_01_legacy/master_algorithms/algorithm_6_policy.json \
    ./benchmark_01_legacy/master_algorithms/

USER medicine
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ['PORT'] + '/health', timeout=3)"

CMD ["sh", "-c", "python -m uvicorn app.api:app --host 0.0.0.0 --port ${PORT} --workers 1"]
