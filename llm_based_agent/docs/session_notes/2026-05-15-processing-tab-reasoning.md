# 2026-05-15 - Processing Tab Reasoning Logs

## Summary
- Added a dedicated Processing tab in the floating chatbot UI to show tool activity per assistant message.
- Persisted thought logs and tool usage in localStorage so the logs survive page reloads.
- Improved frontend handling when tool results arrive without a matching running entry.

## Files Touched
- web/fingerspot.io/engine/resources/views/chatbot/partials/scripts/chat-component.blade.php
- web/fingerspot.io/engine/resources/views/chatbot/partials/scripts/ConversationStorage.blade.php
- web/fingerspot.io/engine/resources/views/chatbot/partials/header.blade.php
- web/fingerspot.io/engine/resources/views/chatbot/partials/chatbot_window.blade.php
- web/fingerspot.io/engine/resources/views/chatbot/partials/processing.blade.php
- web/fingerspot.io/engine/resources/views/chatbot/partials/styles/styles.blade.php

## Notes
- The Processing tab uses the existing tool-call stream to render tool usage without exposing chain-of-thought.
