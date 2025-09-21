FROM python:3.11-slim

# Sistem paketlerini güncelle ve gerekli paketleri yükle
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# Python gereksinimlerini kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Downloads klasörünü oluştur
RUN mkdir -p downloads

# Uygulama dosyalarını kopyala
COPY . .

# Port'u expose et (Railway için)
EXPOSE $PORT

# Uygulamayı başlat
CMD ["python", "main.py"]