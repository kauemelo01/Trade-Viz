import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import subprocess
import tempfile
import shutil
import os
from contextlib import contextmanager

st.set_page_config(page_title="Trading Log Dashboard", layout="wide")
st.title("📈 Trading Log Dashboard")

# ── SSH key from secrets ───────────────────────────────────────────────────────
# Expects .streamlit/secrets.toml to contain:
#
#   [github]
#   ssh_key  = """
#   -----BEGIN OPENSSH PRIVATE KEY-----
#   ...
#   -----END OPENSSH PRIVATE KEY-----
#   """
#   owner    = "your-username"
#   repo     = "your-repo"
#   branch   = "main"
#   filepath = "log.csv"

@contextmanager
def temp_ssh_key(key_content: str):
    """Write the key to a secure temp file, yield its path, then delete it."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
    try:
        tmp.write(key_content)
        tmp.flush()
        tmp.close()
        os.chmod(tmp.name, 0o600)   # SSH refuses keys that are world-readable
        yield tmp.name
    finally:
        os.unlink(tmp.name)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔌 GitHub Source")

    # Pre-fill from secrets if available, allow override in the UI
    cfg = st.secrets.get("github", {})
    owner    = st.text_input("Owner (user or org)", cfg.get("owner", ""))
    repo     = st.text_input("Repository",          cfg.get("repo", ""))
    branch   = st.text_input("Branch",              cfg.get("branch", "main"))
    filepath = st.text_input("File path in repo",   cfg.get("filepath", "log.csv"))
    load_btn = st.button("⬇️ Load from GitHub", use_container_width=True)
    st.divider()
    st.caption("Or upload a local file:")
    uploaded = st.file_uploader("Upload log.csv", type="csv")

# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cloning via SSH…")
def load_from_github(owner, repo, branch, filepath):
    key_content = st.secrets["github"]["ssh_key"]

    with temp_ssh_key(key_content) as key_path:
        tmp_dir = tempfile.mkdtemp()
        try:
            env = {
                **os.environ,
                "GIT_SSH_COMMAND": (
                    f"ssh -i {key_path} "
                    "-o StrictHostKeyChecking=no "
                    "-o BatchMode=yes"
                ),
            }
            subprocess.run(
                [
                    "git", "clone",
                    "--depth=1",
                    "--branch", branch,
                    "--filter=blob:none",
                    "--sparse",
                    f"git@github.com:{owner}/{repo}.git",
                    tmp_dir,
                ],
                env=env, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "sparse-checkout", "set", filepath],
                cwd=tmp_dir, env=env, check=True, capture_output=True, text=True,
            )
            return pd.read_csv(os.path.join(tmp_dir, filepath))
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.stderr or e.stdout or str(e))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

def parse(df):
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="%d %b %H:%M:%S.%f", errors="coerce"
    )
    current_year = pd.Timestamp.now().year
    df["timestamp"] = df["timestamp"].apply(
        lambda t: t.replace(year=current_year) if pd.notna(t) else t
    )
    return df

df = None

if load_btn:
    try:
        df = parse(load_from_github(owner, repo, branch, filepath))
        st.sidebar.success("Loaded from GitHub ✓")
    except KeyError:
        st.sidebar.error("No SSH key found. Add [github] ssh_key to your secrets.toml.")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

if uploaded is not None:
    df = parse(pd.read_csv(uploaded))

if df is None:
    st.info("Connect to GitHub or upload a local `log.csv` to get started.")
    st.stop()

# ── Metrics ────────────────────────────────────────────────────────────────────
profit_df = df.dropna(subset=["profit", "timestamp"]).sort_values("timestamp").copy()
profit_df["cumulative"] = profit_df["profit"].cumsum()

wins   = (profit_df["profit"] > 0).sum()
losses = (profit_df["profit"] < 0).sum()
total  = len(profit_df)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total trades",   total)
col2.metric("Cumulative P&L", f"{profit_df['profit'].sum():.2f}")
col3.metric("Win rate",       f"{wins/total*100:.1f}%" if total else "—")
col4.metric("Wins / Losses",  f"{wins} / {losses}")

# ── Chart ──────────────────────────────────────────────────────────────────────
st.subheader("Profit per Trade  &  Cumulative P&L")

fig = go.Figure()

colors = ["#00c896" if p > 0 else "#ff4b4b" for p in profit_df["profit"]]

fig.add_trace(go.Bar(
    x=profit_df["timestamp"],
    y=profit_df["profit"],
    name="Trade P&L",
    marker_color=colors,
    opacity=0.55,
    customdata=profit_df[["signal_to_wire_ms", "wire_to_confirm_ms"]].values,
    hovertemplate=(
        "<b>%{x}</b><br>"
        "Trade P&L: %{y:.2f}<br>"
        "Signal→Wire: %{customdata[0]:.1f} ms<br>"
        "Wire→Confirm: %{customdata[1]:.1f} ms"
        "<extra></extra>"
    ),
))

fig.add_trace(go.Scatter(
    x=profit_df["timestamp"],
    y=profit_df["cumulative"],
    name="Cumulative P&L",
    mode="lines",
    line=dict(color="#ffffff", width=2.5),
    customdata=profit_df[["signal_to_wire_ms", "wire_to_confirm_ms"]].values,
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

log_df = df[["timestamp", "event", "detail"]].dropna(subset=["detail"]).copy()
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
