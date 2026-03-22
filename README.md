# MedRemind

A Telegram bot that sends medication reminders to a group chat. Admins manage medication schedules for people who may not use Telegram themselves. No accounts, no logins — the group chat is the interface.

## Features

- Scheduled reminders via cron jobs (APScheduler)
- Conversational commands — the bot walks you through each step
- Multiple time slots per medication (up to 4x/day)
- Food rules (before food, after food, empty stomach, etc.)
- Pause/resume without losing data
- Group chat restriction — ignores messages from other chats
- Persists schedules across restarts (SQLite)

## Commands

| Command | Description |
|---|---|
| `/add` | Add a new medication (step-by-step) |
| `/list` | List all medications grouped by person |
| `/pause` | Temporarily pause a medication |
| `/resume` | Resume a paused medication |
| `/delete` | Permanently delete a medication |
| `/addperson` | Add a new person |
| `/help` | Show all commands |

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A Telegram group chat ID (add [@userinfobot](https://t.me/userinfobot) to your group to get the chat ID)

### Install and run

```bash
git clone https://github.com/Maheshkumar-novice/Med-Reminder-Bot.git
cd Med-Reminder-Bot

cp .env.example .env
# Edit .env with your bot token, group chat ID, and person names

uv sync
uv run medremind
```

### Configuration

All configuration is via environment variables (or `.env` file):

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from BotFather |
| `TELEGRAM_GROUP_CHAT_ID` | Yes | — | Target group chat ID (negative number) |
| `DATABASE_URL` | No | `sqlite:///./medremind.db` | Database connection string |
| `TIMEZONE` | No | `Asia/Kolkata` | Timezone for scheduling reminders |
| `PERSONS` | No | `[]` | Initial persons to seed, e.g. `["Alice","Bob"]` |

Persons can also be added at any time via the `/addperson` bot command.

## Reminder format

```
💊 Alice · Metformin 500mg
After food · 8:00 AM
```

## License

MIT
