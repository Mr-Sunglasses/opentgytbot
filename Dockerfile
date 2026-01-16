FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv and set PATH in same layer
ENV PATH="/root/.local/bin:$PATH"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    /root/.local/bin/uv --version

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN /root/.local/bin/uv sync --frozen --no-dev

# Copy application code
COPY . .

# Create downloads directory
RUN mkdir -p downloads

CMD ["/root/.local/bin/uv", "run", "python", "main.py"]
