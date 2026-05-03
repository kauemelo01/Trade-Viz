# Trading Log Dashboard

A Streamlit dashboard that connects to a remote trading bot server via SSH and visualises its activity log in real time.

## What it does

On startup, the dashboard fetches `log.csv` from the remote server over SFTP and displays three sections:

**Summary metrics** — four KPIs computed for the selected time window: total number of trades closed, cumulative P&L, win rate, and the absolute count of winning vs losing trades.

**Profit chart** — an interactive Plotly chart combining two overlaid series:
- Green/red bars (left axis) showing the individual P&L of each closed trade.
- An orange line (right axis) showing the running cumulative P&L across the selected window. The cumulative always restarts from zero at the beginning of the window, so it reflects exactly what you are looking at.

Hovering over any point shows the timestamp, the trade P&L or cumulative value, and the two latency metrics: `signal_to_wire_ms` (time from signal generation to order submission) and `wire_to_confirm_ms` (time from submission to exchange confirmation).

**Event log** — a scrollable table of all rows that carry a `detail` message (bot starts, feed errors, discarded signals, etc.), filtered to the same time window as the chart.

A **time range filter** (date + time pickers) lets you zoom into any sub-period. All three sections — metrics, chart, and event log — update together.

A **Refresh** button clears the cache and re-fetches the latest file from the server.

## Expected log columns

| Column | Description |
|---|---|
| `timestamp` | Event time, format `DD Mon HH:MM:SS.mmm` |
| `profit` | Realised P&L of a closed trade (USD). Rows without a value are non-trade events. |
| `signal_to_wire_ms` | Latency from signal to order submission (ms) |
| `wire_to_confirm_ms` | Latency from order submission to exchange confirmation (ms) |
| `event` | Short event type label |
| `detail` | Human-readable description of the event |

## Security notes

- The RSA private key is stored exclusively in Streamlit secrets and never written to disk. It is loaded into memory via `paramiko.RSAKey.from_private_key()` and discarded after the SFTP session closes.
- The fetched data is cached by Streamlit for the duration of the session. Use the Refresh button to force a new fetch.
- When deploying to Streamlit Community Cloud, paste the contents of `secrets.toml` directly into the Secrets field in the app settings — no file is needed on the server.

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web UI framework |
| `pandas` | Data loading and transformation |
| `plotly` | Interactive chart |
| `paramiko` | SSH/SFTP client |