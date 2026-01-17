FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY metadata_tool/ metadata_tool/
COPY provider/ provider/

# Expose port
EXPOSE 32500

# Run the provider
CMD ["uvicorn", "provider.main:app", "--host", "0.0.0.0", "--port", "32500"]
