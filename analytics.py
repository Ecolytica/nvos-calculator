"""Клиентская аналитика GA4 для Streamlit-интерфейса.

Ключевая идея: gtag.js живёт не в одноразовом iframe компонента, а в
родительском документе Streamlit. Компоненты используются только как «мостик»,
который один раз поднимает gtag наверху и затем вызывает его через
``window.parent``. Благодаря этому:

* у GA4 настоящий ``page_location`` вместо ``about:srcdoc``;
* gtag-экземпляр один на вкладку, а не по одному на каждый iframe;
* события переживают rerun — запрос уходит из родительского документа,
  который Streamlit не пересоздаёт.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

import streamlit as st
from streamlit.components.v1 import html as component_html

_GA4_ID_PATTERN = re.compile(r"^G-[A-Z0-9]+$")
_DEFAULT_GA4_MEASUREMENT_ID = "G-KBKGG5TXDT"


def get_measurement_id() -> str | None:
    """Возвращает валидный GA4 Measurement ID или отключает аналитику."""
    try:
        value = str(
            st.secrets.get("GA4_MEASUREMENT_ID", _DEFAULT_GA4_MEASUREMENT_ID)
        ).strip().upper()
    except Exception:
        value = _DEFAULT_GA4_MEASUREMENT_ID
    return value if _GA4_ID_PATTERN.fullmatch(value) else None


def _bridge_script(measurement_id: str | None) -> str:
    """JS-мостик: поднимает gtag в родительском документе и даёт ecoTrack()."""
    if not measurement_id:
        return "<script>window.ecoTrack=function(){};</script>"
    safe_id = json.dumps(measurement_id)
    return f"""
<script>
(function () {{
  var ID = {safe_id};
  function host() {{
    // Компонент Streamlit рендерится в srcdoc-iframe с allow-same-origin,
    // поэтому родительский документ доступен. Если вдруг нет — работаем
    // локально, чтобы не терять события совсем.
    try {{
      var w = window.parent || window;
      if (w.document && w.document.head) return w;
    }} catch (e) {{}}
    return window;
  }}
  function ensure() {{
    var w = host();
    if (w.__ecolyticaGtag) return w;
    try {{
      w.dataLayer = w.dataLayer || [];
      if (typeof w.gtag !== 'function') {{
        w.gtag = function () {{ w.dataLayer.push(arguments); }};
      }}
      var s = w.document.createElement('script');
      s.async = true;
      s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(ID);
      w.document.head.appendChild(s);
      w.gtag('js', new Date());
      // send_page_view остаётся включённым: config выполняется один раз на
      // загрузку вкладки, поэтому page_view уходит ровно один раз и с
      // настоящим URL страницы.
      w.gtag('config', ID, {{ anonymize_ip: true }});
      w.__ecolyticaGtag = true;
    }} catch (e) {{
      return null;
    }}
    return w;
  }}
  window.ecoTrack = function (name, params) {{
    var w = ensure();
    if (!w || typeof w.gtag !== 'function') return;
    try {{ w.gtag('event', name, params || {{}}); }} catch (e) {{}}
  }};
  ensure();
}})();
</script>
"""


def _component(body: str, *, height: int) -> None:
    measurement_id = get_measurement_id()
    component_html(
        '<!doctype html><html><head><meta charset="utf-8">'
        f"{_bridge_script(measurement_id)}</head>{body}</html>",
        height=height,
        scrolling=False,
    )


def render_page_view() -> None:
    """Поднимает gtag в родительском документе (page_view уходит из config).

    Вызывается на каждом rerun с неизменной разметкой, поэтому Streamlit
    переиспользует один и тот же iframe и повторной инициализации не будет.
    """
    if not get_measurement_id():
        return
    _component('<body style="margin:0"></body>', height=1)


def queue_event(event_name: str, **params: Any) -> None:
    """Ставит безопасное событие в очередь текущей Streamlit-сессии."""
    if not get_measurement_id():
        return
    clean_params = {
        str(key): value
        for key, value in params.items()
        if isinstance(value, (str, int, float, bool))
    }
    sequence = st.session_state.get("_ga4_event_sequence", 0) + 1
    st.session_state["_ga4_event_sequence"] = sequence
    st.session_state.setdefault("_ga4_event_queue", []).append(
        {"name": event_name, "params": clean_params, "token": sequence}
    )


def _render_event(event_name: str, params: dict[str, Any], token: int = 0) -> None:
    event_json = json.dumps(event_name, ensure_ascii=False).replace("</", "<\\/")
    params_json = json.dumps(params, ensure_ascii=False).replace("</", "<\\/")
    _component(
        f'<body style="margin:0;background:transparent" data-event-token="{token}">'
        f"<script>window.ecoTrack({event_json}, {params_json});</script></body>",
        height=1,
    )


def flush_events() -> None:
    """Отправляет накопленные события один раз в том rerun, где они возникли."""
    events = st.session_state.pop("_ga4_event_queue", [])
    if not get_measurement_id():
        return
    for event in events:
        _render_event(event["name"], event["params"], event["token"])


def _tracked_anchor(label: str, url: str, network: str, source: str, *, compact: bool) -> str:
    payload = json.dumps(
        {"network": network, "source": source}, ensure_ascii=False
    ).replace("</", "<\\/")
    click_js = f"window.ecoTrack('social_click', {payload});"
    class_name = "compact" if compact else "button"
    return f"""
<a class="{class_name}" href="{html.escape(url, quote=True)}" target="_blank"
 rel="noopener noreferrer" onclick="{html.escape(click_js, quote=True)}">{html.escape(label)}</a>
"""


def render_sidebar_about() -> None:
    """Показывает информационный sidebar-блок с отслеживаемыми ссылками."""
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
    body = f"""
<style>
*{{box-sizing:border-box}}body{{margin:0;background:transparent;font-family:Arial,sans-serif;color:#55564F}}
.card{{padding:14px;border:1px solid #E2E9DD;border-radius:10px;background:#F6F8F4;font-size:12px;line-height:1.45}}
p{{margin:0 0 9px}}.links{{display:grid;gap:7px;padding-top:3px}}
a{{color:#3B82B8;font-size:12px;font-weight:600;text-decoration:none;overflow-wrap:anywhere}}
a:hover{{color:#2E6F9F;text-decoration:underline}}
</style>
<body><div class="card">
<p>Эколог-проектировщик слишком много времени тратит на ручной поиск данных, сверку таблиц и пересчет показателей.</p>
<p>Этот инструмент — помогает убрать ручную рутину из работы эколога.</p>
<div class="links">{telegram}{vk}</div></div></body>
"""
    _component(body, height=190)


def render_social_button(label: str, url: str, network: str) -> None:
    """Показывает широкую CTA-кнопку и фиксирует переход из результатов."""
    anchor = _tracked_anchor(label, url, network, "results", compact=False)
    body = f"""
<style>
*{{box-sizing:border-box}}body{{margin:0;background:transparent;font-family:Arial,sans-serif}}
a.button{{display:flex;width:100%;height:38px;align-items:center;justify-content:center;padding:0 14px;border:1px solid #357EAF;border-radius:9px;background:#4A91C4;color:#fff;font-size:13px;font-weight:600;text-decoration:none;box-shadow:0 1px 2px rgba(53,126,175,.25)}}
a.button:hover{{background:#357EAF}}
</style><body>{anchor}</body>
"""
    _component(body, height=42)


def render_feedback() -> None:
    """Показывает раскрывающийся блок и считает только первое открытие."""
    body = """
<style>
*{box-sizing:border-box}body{margin:0;background:transparent;font-family:Arial,sans-serif;color:#26261F}
details{border:1px solid #E6E6E1;border-radius:9px;background:#fff;font-size:13px}
summary{cursor:pointer;padding:12px 14px;font-weight:500;list-style-position:inside}
p{margin:0;padding:0 14px 13px;color:#55564F}strong{color:#26261F}
</style>
<body>
<details id="feedback"><summary>Сообщить об ошибке / предложить улучшение</summary>
<p>Напишите мне на почту: <strong>fedor.belyanin@gmail.com</strong></p></details>
<script>
document.getElementById('feedback').addEventListener('toggle', function () {
  const key = 'ecolytica_feedback_opened';
  if (this.open && !sessionStorage.getItem(key)) {
    sessionStorage.setItem(key, '1');
    window.ecoTrack('feedback_open', {});
  }
});
</script></body>
"""
    _component(body, height=92)
