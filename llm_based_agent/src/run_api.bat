@echo off
call conda activate in-app-navigational-agent
uvicorn nkg_agent.api.server:app --reload --port 8001 --no-access-log
