FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_MODEL_SOURCE=BOS

WORKDIR /service
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --fix-missing --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "paddlepaddle==3.2.0" \
       -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
    && pip install --no-cache-dir "paddleocr>=3.5,<4" "fastapi>=0.116,<1" \
       "uvicorn[standard]>=0.35,<1" "python-multipart>=0.0.20,<1" "pillow>=11,<13"

COPY ocr/service.py ./service.py

# Download the official Chinese OCR models while building so runtime remains offline.
RUN python -c "from service import get_engine; get_engine()"

EXPOSE 8001
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
