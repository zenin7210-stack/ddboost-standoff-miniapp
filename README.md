# Arslan Boost Mini App UI

Responsive Telegram Mini App frontend for the approved Arslan Boost look: deep navy background, electric cyan highlights, rank boost order form, balance top-up shortcut, promo code and technical support, order/payment history, settings, and the approved one-second center-neon intro with a discreet `O‘tkazish` skip button.

## Run locally

Serve this folder from a static HTTP server and open `index.html`. Telegram WebApp SDK is loaded from Telegram; outside Telegram the UI falls back to a normal browser preview.

## Telegram integration

- The order form sends a JSON payload with `Telegram.WebApp.sendData()` when opened as a Telegram Mini App. Configure a bot handler for `web_app_data` and validate prices on the server.
- In `config.js`, optionally set public `orderBotUrl` and `supportUrl` links.
- The rank prices are a UI estimate only. The backend must recompute them and validate rank/mode/ID before creating a real order.
- Balance, payments, promo codes, support routing, and order history need the matching server endpoints/bot flows. This frontend intentionally contains no bot token or payment credentials.
- The intro plays once per browser installation; skip is available immediately. The saved reduced-motion setting disables interface motion. The one-second video remains a small local asset.

Rank steps are based on the current bot price table: Calibration → Bronze 3,000; then 4,000, 6,000, 9,000, 13,000, 18,000, 25,000, 35,000, and 50,000 so‘m per next rank.

## Bot

`bot.py` is the existing aiogram order bot with a `web_app_data` handler added. It validates the selected mode and rank progression, recalculates the amount from its server-side price table, saves the order in SQLite, and notifies the admin. Set environment variables from `.env.example` and install `requirements.txt`. Configure your Telegram bot menu button to open the hosted `index.html` as a Web App. For production, add authenticated API routes for balance, promo validation, and history; the current static UI leaves those server-dependent actions as clearly labeled support/prototype flows.
