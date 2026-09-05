# Telegram Daily Data Entry Bot

## Project Overview

This project connects a Telegram bot with a spreadsheet-based workflow to support accurate and smooth daily data entry. It reduces manual errors and improves operational data collection by allowing authorized users to record daily amounts directly from Telegram.

## Features

- Daily data entry through Telegram commands (`/start` and `/add`)
- Interactive location selection using Telegram inline buttons
- Amount validation before saving data
- Automatic matching of the current date in the worksheet
- Spreadsheet integration for recording data in the correct row and column
- Restricted access using allowed Telegram chat IDs
- Clear success and error messages for users

## Tech Stack

- Python
- Telegram Bot API (`python-telegram-bot`)
- Google Sheets API with `gspread`
- Spreadsheet / Excel-style daily workflow
- Git and GitHub

## Deployment

The project is prepared for cloud deployment as a background worker. It can run continuously on platforms such as Railway or an Oracle Cloud virtual machine.

## Security

Secrets are stored in environment variables and must not be committed to GitHub.

Required variables:

```text
TELEGRAM_TOKEN
GOOGLE_CREDENTIALS_JSON
```

Keep service-account JSON files, bot tokens, `.env` files, and local spreadsheet files out of the repository.
