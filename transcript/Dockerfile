# Use a lightweight Python image
FROM python:3.9-slim

# Set working directory inside the container
WORKDIR /app

# Install required Python dependencies
RUN pip install python-multipart fastapi uvicorn faster-whisper

WORKDIR /app
COPY transcriptServer.py /app

RUN mkdir -p /var/models && \
    python -c "from faster_whisper.utils import download_model; download_model('turbo', output_dir='/var/models')"

# Expose port 8888 for external access
EXPOSE 8888

# Run the web service
CMD ["uvicorn", "transcriptServer:app", "--host", "0.0.0.0", "--port", "8888"]
