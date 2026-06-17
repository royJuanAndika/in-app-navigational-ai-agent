#!/bin/bash
uvicorn nkg_agent.api.server:app --reload --host 0.0.0.0 --port 8001 --no-access-log
