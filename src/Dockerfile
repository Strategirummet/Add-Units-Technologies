# syntax=docker/dockerfile:1
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy only lockfiles first (cache-friendly)
COPY pyproject.toml uv.lock ./

# Create venv
RUN uv venv /opt/venv

# Force uv to use THIS environment
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Install deps into /opt/venv
RUN uv sync --frozen --no-dev --python /opt/venv/bin/python

# Copy app source
COPY . .

EXPOSE 8000

# Run uvicorn from the venv
CMD ["/opt/venv/bin/python", "-m", "uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000"]
