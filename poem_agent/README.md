# Intelligent AI Poem Channel Management Agent

An owner-controlled bot for poem collection, classification, duplicate-aware selection, image discovery, approval, and Telegram channel publishing. The project is poetry-first; AI is optional and cannot bypass approval or security gates.

## Setup

Requires Python 3.11+. From this directory:

```sh
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
cp .env.example .env
python main.py --check
```

Set `OWNER_TELEGRAM_ID` and `TELEGRAM_BOT_TOKEN` in `.env`, add the bot as an administrator with posting permission to each destination channel, then run `python main.py --poll`. Telegram bots can only receive channel posts when added and granted the relevant access; this project does not scrape arbitrary private channels. MTProto support is an optional adapter point, not enabled by default.

## Workflow and safety

Owner messages can add/analyze poems, create drafts, request deletion, and prepare posts. Publishing and destructive actions require owner authorization and explicit approval. A proposed post is stored as a draft; nothing publishes merely because a model suggested it. Original poem text is preserved. Attribution should be verified before publication. Review image provider license and attribution data for each result.

AI model calls are optional. Configure a supported provider and model in environment variables; absence of credentials means deterministic local intent and poem-analysis features only. Provider outages are reported rather than represented as successful model calls. Never put API keys into poems, chats, memory, or source control.

## Testing

```sh
python -m pytest -q
python -m compileall -q .
python line_check.py
```

The line checker enforces the historical 301–399-line policy for designated core modules; modules are not padded with meaningless code. A failing report is intentional disclosure, not evidence that checks passed.

## Limitations

Heuristic emotion/theme analysis is not literary judgment and Burmese classification should be owner-reviewed. Image sources are individually optional; network access, terms, attribution, and image validity must be checked. Telegram analytics are limited to data accessible to the bot. Scheduling requires the application process to remain running. Production deployment should use a process supervisor, backups, TLS outbound controls, and a database migration strategy.
