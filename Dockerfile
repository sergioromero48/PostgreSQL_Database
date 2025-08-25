# Database/Dockerfile
# Use Python 3.10 slim (multi-arch: arm64 & amd64)
FROM --platform=amd64 python:3.10-slim

# avoid buffering (so logs show up immediately)
ENV PYTHONUNBUFFERED=1

# install OS-level build deps for Streamlit
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      gcc \
      curl && \
    rm -rf /var/lib/apt/lists/*

# create app directory
WORKDIR /app

# install pip dependencies
# (Assumes you have a requirements.txt listing streamlit, psycopg2, serial, pandas, etc.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy your code
COPY . .

# expose Streamlit default port
EXPOSE 8501

# default command
#CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
CMD ["bash", "-c", "streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true"]
