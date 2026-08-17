FROM python:3.12-slim

WORKDIR /harvester

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Mount data/overrides as a volume to supply curated YAML at build time
VOLUME ["/harvester/data/overrides"]

ENTRYPOINT ["harvest"]
CMD ["--output", "/output/compat.db"]
