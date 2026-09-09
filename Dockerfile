FROM python:3.12-alpine
WORKDIR /app
COPY server.py demo.py ./
CMD ["python", "demo.py"]
