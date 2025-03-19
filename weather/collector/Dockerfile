# Stage 1: Builder (Debian-based full image)
FROM python:3.12-slim AS builder

# Install build tools (g++, make, etc.)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Set work directory in builder
WORKDIR /install

# Copy requirements.txt into the builder image
COPY requirements.txt .

# Upgrade pip and install dependencies into /install (using --target)
RUN pip install -r requirements.txt

# (Optional) You can also pre-install any other build-time tools if needed

# Stage 2: Final Image (AWS Lambda runtime)
FROM public.ecr.aws/lambda/python:3.12

# Copy the pre-built Python packages from builder stage into the final image's site-packages.
# AWS Lambda Python base images typically store packages in /var/lang/lib/python3.12/site-packages.
COPY --from=builder /install/ /var/lang/lib/python3.12/site-packages/

# Copy your collector script
COPY collector.py ./

# Install Playwright browsers (Chromium)
# (Since playwright may need to download its browser binaries at runtime, we do this here.)
RUN pip install --upgrade pip && python -m playwright install chromium

# Set the Lambda entry point (the function Lambda calls)
CMD ["collector.lambda_handler"]
