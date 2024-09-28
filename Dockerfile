FROM apache/airflow:2.10.1-python3.12

USER root
RUN apt-get update && apt-get install -y git
USER airflow