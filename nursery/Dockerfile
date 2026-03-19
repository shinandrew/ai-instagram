FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# Install the SDK from local source (no PyPI publishing needed)
COPY sdk/ ./sdk/
RUN pip install --no-cache-dir "./sdk[openai]"

# Install remaining nursery dependencies
COPY nursery/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nursery/main.py .
COPY nursery/avatar.py .

CMD ["python", "-u", "main.py"]
