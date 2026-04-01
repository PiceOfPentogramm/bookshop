#!/bin/bash
until nc -z postgres 5432; do sleep 1; done
until nc -z user-service 8001; do sleep 1; done
until nc -z book-service 8002; do sleep 1; done
until nc -z rabbitmq 5672; do sleep 1; done
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8003
