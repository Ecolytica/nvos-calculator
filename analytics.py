"""Необязательная клиентская аналитика GA4 для Streamlit-интерфейса."""

from __future__ import annotations

import html
import json
import re
from typing import Any

import streamlit as st
from streamlit.components.v1 import html as component_html

_GA4_ID_PATTERN = re.compile(r"^G-[A-Z0-9]+$")
_DEFAULT_GA4_MEASUREMENT_ID = "G-KBKGG5TXDT"
_APP_URL = "https://ecolytica-nvos.streamlit.app/"


def get_measurement_id() -> str | None:
    """Возвращает валидный GA4 Measurement ID или отключает аналитику."""
    try:
        value = str(
            st.secrets.get("GA4_MEASUREMENT_ID", _DEFAULT_GA4_MEASUREMENT_ID)
        ).strip().upper()
    except Exception:
        value = _DEFAULT_GA4_MEASUREMENT_ID
    return value if _GA4_ID_PATTERN.fullmatch(value) else None


def _gtag_bootstrap(measurement_id: str | None) -> str:
    if not measurement_id:
        return ""
    safe_id = json.dumps(measurement_id)
    return f"""
<script async src="https://www.googletagmanager.com/gtag/js?id={html.escape(measurement_id)}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag() {{ dataLayer.push(arguments); }}
gtag('js', new Date());
gtag('config', {safe_id}, {{send_page_view: false, anonymize_ip: true}});
</script>
"""


def queue_event(event_name: str, **params: Any) -> None:
    """Ставит безопасное событие в очередь текущей Streamlit-сессии."""
    if not get_measurement_id():
        return
    clean_params = {
        str(key): value
        for key, value in params.items()
        if isinstance(value, (str, int, float, bool))
    }
    clean_params.setdefault("page_location", _APP_URL)
    sequence = st.session_state.get("_ga4_event_sequence", 0) + 1
    st.session_state["_ga4_event_sequence"] = sequence
    st.session_state.setdefault("_ga4_event_queue", []).append(
        {"name": event_name, "params": clean_params, "token": sequence}
    )


def render_page_view() -> None:
    """Регистрирует одно открытие на Streamlit-сессию, а не на каждый rerun."""
    measurement_id = get_measurement_id()
    if not measurement_id:
        return
    should_send = not st.session_state.get("_ga4_page_view_sent")
    st.session_state["_ga4_page_view_sent"] = True

    # Keep this component at the same Streamlit delta path on every rerun. If
    # it disappears, Streamlit removes the iframe and may abort gtag.js before
    # its queued page_view has been transmitted.
    if should_send:
        _render_event(
            "page_view",
            {
                "page_location": _APP_URL,
                "page_title": "Калькулятор платы за выбросы в атмосферу",
            },
            measurement_id,
        )
    else:
        component_html(
            f'<!doctype html><html><head><meta charset="utf-8">'
            f'{_gtag_bootstrap(measurement_id)}</head><body></body></html>',
            height=1,
            scrolling=False,
        )


def _render_event(event_name: str, params: dict[str, Any], measurement_id: str, token: int = 0) -> None:
    event_json = json.dumps(event_name, ensure_ascii=False).replace("</", "<\\/")
    params_json = json.dumps(params, ensure_ascii=False).replace("</", "<\\/")
    markup = f"""
<!doctype html><html><head><meta charset="utf-8">{_gtag_bootstrap(measurement_id)}</head>
<body style="margin:0;background:transparent" data-event-token="{token}">
<script>
gtag('event', {event_json}, Object.assign({{}}, {params_json}, {{transport_type: 'beacon'}}));
</script></body></html>
"""
    # Keep the analytics iframe renderable while remaining visually hidden.
    component_html(markup, height=1, scrolling=False)


def flush_events() -> None:
    """Отправляет накопленные события один раз в том rerun, где они возникли."""
    events = st.session_state.pop("_ga4_event_queue", [])
    measurement_id = get_measurement_id()
    if not measurement_id:
        return
    for event in events:
        _render_event(event["name"], event["params"], measurement_id, event["token"])


def _tracked_anchor(label: str, url: str, network: str, source: str, *, compact: bool) -> str:
    measurement_id = get_measurement_id()
    payload = json.dumps(
        {
            "network": network,
            "source": source,
            "page_location": _APP_URL,
            "transport_type": "beacon",
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    click_js = f"gtag('event', 'social_click', {payload});" if measurement_id else ""
    class_name = "compact" if compact else "button"
    return f"""
<a class="{class_name}" href="{html.escape(url, quote=True)}" target="_blank"
 rel="noopener noreferrer" onclick="{html.escape(click_js, quote=True)}">{html.escape(label)}</a>
"""


def render_sidebar_about() -> None:
    """Показывает информационный sidebar-блок с отслеживаемыми ссылками."""
    measurement_id = get_measurement_id()
    telegram = _tracked_anchor(
        "Telegram: Только без рук", "https://t.me/ecology_start", "telegram", "sidebar", compact=True
    )
    vk = _tracked_anchor(
        "ВК: Экология без ручной рутины | Ecolytica",
        "https://vk.ru/ecolytica",
        "vk",
        "sidebar",
        compact=True,
    )
    markup = f"""
<!doctype html><html><head><meta charset="utf-8">{_gtag_bootstrap(measurement_id)}
<style>
*{{box-sizing:border-box}}body{{margin:0;background:transparent;font-family:Arial,sans-serif;color:#55564F}}
.card{{padding:14px;border:1px solid #E2E9DD;border-radius:10px;background:#F6F8F4;font-size:12px;line-height:1.45}}
p{{margin:0 0 9px}}.links{{display:grid;gap:7px;padding-top:3px}}
a{{color:#3B82B8;font-size:12px;font-weight:600;text-decoration:none;overflow-wrap:anywhere}}
a:hover{{color:#2E6F9F;text-decoration:underline}}
</style></head><body><div class="card">
<p>Эколог-проектировщик слишком много времени тратит на ручной поиск данных, сверку таблиц и пересчет показателей.</p>
<p>Этот инструмент — помогает убрать ручную рутину из работы эколога.</p>
<div class="links">{telegram}{vk}</div></div></body></html>
"""
    component_html(markup, height=190, scrolling=False)


def render_social_button(label: str, url: str, network: str) -> None:
    """Показывает широкую CTA-кнопку и фиксирует переход из результатов."""
    measurement_id = get_measurement_id()
    anchor = _tracked_anchor(label, url, network, "results", compact=False)
    markup = f"""
<!doctype html><html><head><meta charset="utf-8">{_gtag_bootstrap(measurement_id)}
<style>
*{{box-sizing:border-box}}body{{margin:0;background:transparent;font-family:Arial,sans-serif}}
a.button{{display:flex;width:100%;height:38px;align-items:center;justify-content:center;padding:0 14px;border:1px solid #357EAF;border-radius:9px;background:#4A91C4;color:#fff;font-size:13px;font-weight:600;text-decoration:none;box-shadow:0 1px 2px rgba(53,126,175,.25)}}
a.button:hover{{background:#357EAF}}
</style></head><body>{anchor}</body></html>
"""
    component_html(markup, height=42, scrolling=False)


def render_feedback() -> None:
    """Показывает раскрывающийся блок и считает только первое открытие."""
    measurement_id = get_measurement_id()
    event_js = f"gtag('event', 'feedback_open', {{page_location: {json.dumps(_APP_URL)}, transport_type: 'beacon'}});" if measurement_id else ""
    markup = f"""
<!doctype html><html><head><meta charset="utf-8">{_gtag_bootstrap(measurement_id)}
<style>
*{{box-sizing:border-box}}body{{margin:0;background:transparent;font-family:Arial,sans-serif;color:#26261F}}
details{{border:1px solid #E6E6E1;border-radius:9px;background:#fff;font-size:13px}}
summary{{cursor:pointer;padding:12px 14px;font-weight:500;list-style-position:inside}}
p{{margin:0;padding:0 14px 13px;color:#55564F}}strong{{color:#26261F}}
</style></head><body>
<details id="feedback"><summary>Сообщить об ошибке / предложить улучшение</summary>
<p>Напишите мне на почту: <strong>fedor.belyanin@gmail.com</strong></p></details>
<script>
document.getElementById('feedback').addEventListener('toggle', function () {{
  const key = 'ecolytica_feedback_opened';
  if (this.open && !sessionStorage.getItem(key)) {{
    sessionStorage.setItem(key, '1');
    {event_js}
  }}
}});
</script></body></html>
"""
    component_html(markup, height=92, scrolling=False)
