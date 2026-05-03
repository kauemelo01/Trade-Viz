import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import paramiko
import io

st.set_page_config(page_title="Trading Log Dashboard", layout="wide")
st.title("📈 Trading Log Dashboard")

# ── Load CSV from Oracle server via SSH ────────────────────────────────────────
@st.cache_data(show_spinner="Connecting via SSH…")
def load_data():
    key_content = st.secrets["ssh"]["rsa_key"]
    host        = st.secrets["ssh"]["host"]
    user        = st.secrets["ssh"]["user"]
    remote_path = st.secrets["ssh"]["csv_path"]

    pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_content))
    ssh  = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, pkey=pkey)

    sftp = ssh.open_sftp()
    with sftp.open(remote_path, "r") as f:
        content = f.read()
    sftp.close()
    ssh.close()

    return pd.read_csv(io.BytesIO(content))

def parse(df):
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="%d %b %H:%M:%S.%f", errors="coerce"
    )
    current_year = pd.Timestamp.now().year
    df["timestamp"] = df["timestamp"].apply(
        lambda t: t.replace(year=current_year) if pd.notna(t) else t
    )
    return df

# ── Fetch ──────────────────────────────────────────────────────────────────────
try:
    df = parse(load_data())
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

# ── Time range filter ──────────────────────────────────────────────────────────
profit_df = df.dropna(subset=["profit", "timestamp"]).sort_values("timestamp").copy()

t_min = profit_df["timestamp"].min()
t_max = profit_df["timestamp"].max()

st.subheader("⏱ Time Range")

col_from, col_to = st.columns(2)

with col_from:
    date_from = st.date_input("From date", value=t_min.date(), min_value=t_min.date(), max_value=t_max.date())
    time_from = st.time_input("From time", value=t_min.time())

with col_to:
    date_to = st.date_input("To date", value=t_max.date(), min_value=t_min.date(), max_value=t_max.date())
    time_to = st.time_input("To time", value=t_max.time())

ts_from = pd.Timestamp.combine(date_from, time_from)
ts_to   = pd.Timestamp.combine(date_to,   time_to)

if ts_from >= ts_to:
    st.warning("'From' must be earlier than 'To'.")
    st.stop()

# Apply filter — cumulative restarts from zero within the selected window
mask      = (profit_df["timestamp"] >= ts_from) & (profit_df["timestamp"] <= ts_to)
filtered  = profit_df[mask].copy()
filtered["cumulative"] = filtered["profit"].cumsum()

# ── Metrics ────────────────────────────────────────────────────────────────────
wins   = (filtered["profit"] > 0).sum()
losses = (filtered["profit"] < 0).sum()
total  = len(filtered)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total trades",   total)
col2.metric("Cumulative P&L", f"{filtered['profit'].sum():.2f}")
col3.metric("Win rate",       f"{wins/total*100:.1f}%" if total else "—")
col4.metric("Wins / Losses",  f"{wins} / {losses}")

# ── Chart ──────────────────────────────────────────────────────────────────────
st.subheader("Profit per Trade  &  Cumulative P&L")

if filtered.empty:
    st.info("No trades in the selected time range.")
else:
    fig = go.Figure()

    colors = ["#00c896" if p > 0 else "#ff4b4b" for p in filtered["profit"]]

    fig.add_trace(go.Bar(
        x=filtered["timestamp"],
        y=filtered["profit"],
        name="Trade P&L",
        marker_color=colors,
        opacity=0.55,
        customdata=filtered[["signal_to_wire_ms", "wire_to_confirm_ms"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Trade P&L: %{y:.2f}<br>"
            "Signal→Wire: %{customdata[0]:.1f} ms<br>"
            "Wire→Confirm: %{customdata[1]:.1f} ms"
            "<extra></extra>"
        ),
    ))

    fig.add_trace(go.Scatter(
        x=filtered["timestamp"],
        y=filtered["cumulative"],
        name="Cumulative P&L",
        mode="lines",
        line=dict(color="#ffffff", width=2.5),
        customdata=filtered[["signal_to_wire_ms", "wire_to_confirm_ms"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Cumulative: %{y:.2f}<br>"
            "Signal→Wire: %{customdata[0]:.1f} ms<br>"
            "Wire→Confirm: %{customdata[1]:.1f} ms"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        height=420,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, title="Time"),
        yaxis=dict(showgrid=True, gridcolor="#333", title="Profit (USD)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        barmode="overlay",
    )

    st.plotly_chart(fig, use_container_width=True)

# ── Detail log ─────────────────────────────────────────────────────────────────
st.subheader("📋 Event Log")

log_df = (
    df[["timestamp", "event", "detail"]]
    .dropna(subset=["detail"])
    .copy()
)
# Also filter the event log to the selected window
log_df = log_df[
    (log_df["timestamp"] >= ts_from) & (log_df["timestamp"] <= ts_to)
]
log_df["timestamp"] = log_df["timestamp"].astype(str)

st.dataframe(
    log_df.reset_index(drop=True),
    use_container_width=True,
    height=350,
    column_config={
        "timestamp": st.column_config.TextColumn("Timestamp", width=190),
        "event":     st.column_config.TextColumn("Event",     width=160),
        "detail":    st.column_config.TextColumn("Detail"),
    },
)
