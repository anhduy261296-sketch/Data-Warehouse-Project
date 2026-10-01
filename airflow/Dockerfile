FROM apache/airflow:2.11.2

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends unixodbc-dev \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
