"""
Cycle reporter & email notification system.

After each agent cycle, builds a structured report and sends it via email.
Also saves an HTML report to disk as backup.

Requires Gmail App Password for email delivery.
Setup: https://myaccount.google.com/apppasswords
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from agents import hub
from agents.config import (
    CONTENT_DIR,
    NOTIFY_EMAIL,
    NOTIFY_EMAIL_PASSWORD,
    NOTIFY_SMTP_PORT,
    NOTIFY_SMTP_SERVER,
    REPORTS_DIR,
    SITE_NAME,
    SITE_URL,
)

logger = logging.getLogger(__name__)


def build_cycle_report(
    results: list[dict[str, Any]],
    iteration: int,
    pipeline: list[str],
) -> dict[str, Any]:
    """Build a structured report from cycle results.

    Returns a dict with all report data + rendered HTML.
    """
    now = datetime.now()
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    err_count = len(results) - ok_count
    total = len(results)

    # Determine overall health
    if err_count == 0:
        health = "EXCELLENT"
        health_color = "#10b981"
        health_emoji = "OK"
    elif err_count <= 1:
        health = "BON"
        health_color = "#f59e0b"
        health_emoji = "ATTENTION"
    else:
        health = "CRITIQUE"
        health_color = "#ef4444"
        health_emoji = "ERREUR"

    # Collect details per agent
    agent_details: list[dict[str, Any]] = []
    for i, (agent_key, result) in enumerate(zip(pipeline, results)):
        agent_details.append({
            "name": agent_key.upper(),
            "status": result.get("status", "unknown"),
            "summary": result.get("summary", "(pas de resume)"),
            "error": result.get("error", ""),
        })

    # Count articles
    article_count = 0
    if CONTENT_DIR.exists():
        article_count = len(list(CONTENT_DIR.glob("*.md")))

    # New articles created this cycle
    new_articles = []
    for r in results:
        if r.get("articles"):
            new_articles.extend(r["articles"])

    # Build report data
    report = {
        "timestamp": now.isoformat(),
        "date_formatted": now.strftime("%d/%m/%Y a %H:%M"),
        "iteration": iteration,
        "health": health,
        "health_color": health_color,
        "health_emoji": health_emoji,
        "ok_count": ok_count,
        "err_count": err_count,
        "total": total,
        "agent_details": agent_details,
        "article_count": article_count,
        "new_articles": new_articles,
    }

    # Render HTML
    report["html"] = _render_html(report)
    report["text"] = _render_text(report)

    return report


def _render_html(report: dict[str, Any]) -> str:
    """Render the report as a styled HTML email."""
    agents_rows = ""
    for a in report["agent_details"]:
        status_icon = "[OK]" if a["status"] == "ok" else "[ERREUR]"
        status_color = "#10b981" if a["status"] == "ok" else "#ef4444"
        error_line = f"<br><small style='color:#ef4444'>{a['error']}</small>" if a["error"] else ""
        agents_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{a['name']}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb;color:{status_color}">{status_icon}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb">{a['summary'][:120]}{error_line}</td>
        </tr>"""

    new_articles_html = ""
    if report["new_articles"]:
        items = "".join(f"<li>{a}</li>" for a in report["new_articles"])
        new_articles_html = f"""
        <div style="margin:16px 0;padding:12px;background:#f0fdf4;border-radius:8px">
            <strong>Nouveaux articles :</strong>
            <ul style="margin:8px 0">{items}</ul>
        </div>"""

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1f2937">

    <div style="text-align:center;padding:20px;background:linear-gradient(135deg,#059669,#10b981);border-radius:12px;color:white;margin-bottom:24px">
        <h1 style="margin:0;font-size:22px">{SITE_NAME}</h1>
        <p style="margin:4px 0 0;opacity:0.9">Rapport du cycle #{report['iteration']}</p>
        <p style="margin:4px 0 0;opacity:0.8;font-size:13px">{report['date_formatted']}</p>
    </div>

    <div style="text-align:center;padding:16px;background:{report['health_color']}15;border:2px solid {report['health_color']};border-radius:10px;margin-bottom:20px">
        <span style="font-size:28px;font-weight:700;color:{report['health_color']}">{report['health_emoji']}</span>
        <p style="margin:4px 0 0;font-size:18px;font-weight:600;color:{report['health_color']}">
            Sante : {report['health']}
        </p>
        <p style="margin:4px 0 0;color:#6b7280">
            {report['ok_count']}/{report['total']} agents OK | {report['article_count']} articles au total
        </p>
    </div>

    <h2 style="font-size:16px;color:#374151;border-bottom:2px solid #e5e7eb;padding-bottom:8px">
        Detail par agent
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead>
            <tr style="background:#f9fafb">
                <th style="padding:8px;text-align:left;border-bottom:2px solid #e5e7eb">Agent</th>
                <th style="padding:8px;text-align:left;border-bottom:2px solid #e5e7eb">Statut</th>
                <th style="padding:8px;text-align:left;border-bottom:2px solid #e5e7eb">Resume</th>
            </tr>
        </thead>
        <tbody>{agents_rows}</tbody>
    </table>

    {new_articles_html}

    <div style="margin-top:24px;padding:12px;background:#f3f4f6;border-radius:8px;font-size:12px;color:#6b7280;text-align:center">
        <a href="{SITE_URL}" style="color:#059669">{SITE_URL}</a><br>
        Rapport automatique genere par l'equipe IA de {SITE_NAME}
    </div>

</body>
</html>"""


def _render_text(report: dict[str, Any]) -> str:
    """Render a plain-text version of the report."""
    lines = [
        f"=== {SITE_NAME} - Rapport Cycle #{report['iteration']} ===",
        f"Date : {report['date_formatted']}",
        f"Sante : {report['health']} ({report['ok_count']}/{report['total']} OK)",
        f"Articles total : {report['article_count']}",
        "",
        "--- Detail agents ---",
    ]
    for a in report["agent_details"]:
        status = "OK" if a["status"] == "ok" else "ERREUR"
        lines.append(f"  [{status}] {a['name']} : {a['summary'][:100]}")
        if a["error"]:
            lines.append(f"         ERREUR: {a['error'][:100]}")

    if report["new_articles"]:
        lines.append("")
        lines.append("--- Nouveaux articles ---")
        for a in report["new_articles"]:
            lines.append(f"  + {a}")

    lines.append("")
    lines.append(f"-- {SITE_URL} --")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Save report to disk
# ------------------------------------------------------------------

def save_report(report: dict[str, Any]) -> Path:
    """Save the HTML report to disk."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"cycle-{report['iteration']}-{datetime.now().strftime('%Y%m%d-%H%M')}.html"
    filepath = REPORTS_DIR / filename
    filepath.write_text(report["html"], encoding="utf-8")
    logger.info("Report saved: %s", filepath)
    return filepath


# ------------------------------------------------------------------
# Send email
# ------------------------------------------------------------------

def send_email_report(report: dict[str, Any]) -> bool:
    """Send the cycle report via Gmail.

    Returns True if sent successfully, False otherwise.
    Silently skips if email is not configured.
    """
    if not NOTIFY_EMAIL or not NOTIFY_EMAIL_PASSWORD:
        logger.info("Email not configured (NOTIFY_EMAIL / NOTIFY_EMAIL_PASSWORD). Skipping.")
        return False

    subject = (
        f"[{report['health_emoji']}] {SITE_NAME} - Cycle #{report['iteration']} "
        f"({report['ok_count']}/{report['total']} OK)"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = NOTIFY_EMAIL
    msg["To"] = NOTIFY_EMAIL

    # Attach both text and HTML versions
    msg.attach(MIMEText(report["text"], "plain", "utf-8"))
    msg.attach(MIMEText(report["html"], "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(NOTIFY_SMTP_SERVER, NOTIFY_SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(NOTIFY_EMAIL, NOTIFY_EMAIL_PASSWORD)
            server.send_message(msg)

        logger.info("Email report sent to %s", NOTIFY_EMAIL)
        return True

    except Exception as exc:
        logger.error("Failed to send email report: %s", exc)
        return False


# ------------------------------------------------------------------
# Main entry point (called by orchestrator)
# ------------------------------------------------------------------

def report_cycle(
    results: list[dict[str, Any]],
    iteration: int,
    pipeline: list[str],
) -> dict[str, Any]:
    """Build, save, and send the cycle report.

    Returns the report data dict.
    """
    report = build_cycle_report(results, iteration, pipeline)

    # Always save to disk
    filepath = save_report(report)
    logger.info("Rapport HTML : %s", filepath)

    # Send email if configured
    email_sent = send_email_report(report)
    if email_sent:
        hub.log_action("Reporter", f"Email envoye (cycle #{iteration})", status="ok")
    else:
        hub.log_action(
            "Reporter",
            f"Rapport sauvegarde (cycle #{iteration}) - email non configure",
            status="ok",
        )

    return report
