FROM python:3.11-slim

# Install system dependencies including Git and Node.js
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy Python requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend application code
COPY . .

# Note: Render dynamically assigns a port via the PORT environment variable.
# We expose 8080 as a fallback for local development.
EXPOSE 8080

# Command to run the application using the start script
CMD ["./start.sh"]
