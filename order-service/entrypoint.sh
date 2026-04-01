#!/bin/bash
until nc -z postgres 5432; do sleep 1; done
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8003
