FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# Install deps from both worker and nursery (same aigram[openai] base)
COPY worker/requirements.txt ./worker-requirements.txt
COPY nursery/requirements.txt ./nursery-requirements.txt
RUN pip install --no-cache-dir -r worker-requirements.txt -r nursery-requirements.txt

# Install local SDK, overriding the PyPI version so brain prompt changes apply immediately
COPY sdk/ ./sdk/
RUN pip install --no-cache-dir --no-deps ./sdk/

COPY worker/main.py ./worker_main.py
COPY nursery/main.py ./nursery_main.py
COPY nursery/avatar.py ./avatar.py

# WORKER_MODE=nursery → runs nursery_main.py
# WORKER_MODE unset   → runs worker_main.py (default)
CMD sh -c 'if [ "$WORKER_MODE" = "nursery" ]; then exec python -u nursery_main.py; else exec python -u worker_main.py; fi'
