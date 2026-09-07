# One image, two entrypoints (see docker-compose.prod.yml's `command:` per
# service) -- codejudge_mcp and codejudge_ai are the same distribution
# already (one pyproject.toml, setuptools finds both packages).
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY codejudge_ai ./codejudge_ai
COPY codejudge_mcp ./codejudge_mcp
COPY adk_app ./adk_app
COPY server.py ./server.py

RUN pip install --no-cache-dir -e ".[agent,persist]"

# Default to the agent's HTTP server; docker-compose overrides this for the
# mcp service with `command: python -m codejudge_mcp`.
CMD ["python", "server.py"]
