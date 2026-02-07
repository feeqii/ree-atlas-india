FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GDAL_MEM_ENABLE_OPEN=YES \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev \
    libgeos-dev libproj-dev proj-bin \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app
COPY requirements.txt ./
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir setuptools wheel cython numpy==1.26.4 \
    && pip install --no-cache-dir --no-build-isolation rasterio==1.3.10 \
    && pip install --no-cache-dir --prefer-binary --no-build-isolation -r requirements.txt

COPY app ./app
COPY tests ./tests

EXPOSE 8000
