"""Mermaid diagram renderer with interactive pan/zoom, fullscreen, SVG download, and Graphviz fallback."""
from __future__ import annotations

import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ASSETS_JS = Path(__file__).resolve().parent.parent / "assets" / "mermaid.min.js"
CDN_URL = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"


def render_mermaid(src: str, *, height: int = 460, dot_fallback: str | None = None) -> None:
    """Render an interactive Mermaid diagram with pan, zoom, fullscreen, and SVG download."""
    if ASSETS_JS.is_file():
        js_text = ASSETS_JS.read_text(encoding="utf-8", errors="ignore")
        loader = f"<script>{js_text}</script>"
    else:
        loader = f'<script src="{CDN_URL}"></script>'

    escaped = html.escape(src)
    page_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0; background: #FFFFFF;
    font-family: Inter, system-ui, -apple-system, sans-serif;
    overflow: hidden;
  }}
  #wrap {{
    position: relative; width: 100%; height: 100vh;
    background: #FFFFFF; border-radius: 8px; overflow: hidden;
    cursor: grab; user-select: none;
  }}
  #wrap:active {{ cursor: grabbing; }}
  #toolbar {{
    position: absolute; top: 10px; right: 10px; z-index: 20;
    display: flex; gap: 6px; align-items: center;
    background: rgba(255,255,255,0.94); border: 1px solid #E2E8F0;
    border-radius: 8px; padding: 4px 6px;
    box-shadow: 0 2px 6px rgba(15,23,42,0.08);
  }}
  .tbtn {{
    border: 1px solid #E2E8F0; background: #F8FAFC; color: #0F172A;
    font-size: 12px; font-weight: 600; padding: 4px 8px; border-radius: 6px;
    cursor: pointer; line-height: 1.2;
  }}
  .tbtn:hover {{ background: #FFF1E8; border-color: #FF5F00; color: #9A3412; }}
  .tbtn.primary {{ background: #FF5F00; color: #FFFFFF; border-color: #FF5F00; }}
  .tbtn.primary:hover {{ background: #E05300; }}
  #zoomLbl {{ font-size: 11px; color: #475569; min-width: 38px; text-align: center; font-variant-numeric: tabular-nums; }}
  #stage {{
    width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
    transform-origin: center center;
  }}
  .mermaid svg {{ max-width: none !important; height: auto; }}
  .fallback {{
    display: none; padding: 16px; margin: 16px; border: 1px solid #E2E8F0;
    border-radius: 8px; background: #F8FAFC; color: #475569; font-size: 13px;
  }}
  #hint {{
    position: absolute; bottom: 8px; left: 12px; font-size: 11px; color: #94A3B8;
    pointer-events: none;
  }}
</style>
{loader}
</head>
<body>
  <div id="wrap">
    <div id="toolbar">
      <button class="tbtn" id="zoomOut" title="Zoom out">−</button>
      <span id="zoomLbl">100%</span>
      <button class="tbtn" id="zoomIn" title="Zoom in">+</button>
      <button class="tbtn" id="resetBtn" title="Reset view">Reset</button>
      <button class="tbtn" id="fsBtn" title="Toggle fullscreen">Fullscreen</button>
      <button class="tbtn primary" id="dlBtn" title="Download SVG">Download SVG</button>
    </div>
    <div id="stage">
      <div class="mermaid" id="mmd">{escaped}</div>
    </div>
    <div id="hint">Drag to pan · Scroll to zoom</div>
    <div class="fallback" id="fb">Mermaid JS unavailable (offline without vendored assets). See Mermaid source below.</div>
  </div>
  <script>
    (function() {{
      const wrap = document.getElementById("wrap");
      const stage = document.getElementById("stage");
      const zoomLbl = document.getElementById("zoomLbl");
      let scale = 1.0, tx = 0, ty = 0, dragging = false, sx = 0, sy = 0;

      function apply() {{
        stage.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
        zoomLbl.textContent = Math.round(scale * 100) + "%";
      }}

      document.getElementById("zoomIn").onclick = () => {{ scale = Math.min(4, scale * 1.2); apply(); }};
      document.getElementById("zoomOut").onclick = () => {{ scale = Math.max(0.3, scale / 1.2); apply(); }};
      document.getElementById("resetBtn").onclick = () => {{ scale = 1.0; tx = 0; ty = 0; apply(); }};

      wrap.addEventListener("wheel", (e) => {{
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        scale = Math.max(0.3, Math.min(4, scale * factor));
        apply();
      }}, {{ passive: false }});

      wrap.addEventListener("mousedown", (e) => {{
        if (e.target.closest("#toolbar")) return;
        dragging = true; sx = e.clientX - tx; sy = e.clientY - ty;
      }});
      window.addEventListener("mousemove", (e) => {{
        if (!dragging) return;
        tx = e.clientX - sx; ty = e.clientY - sy; apply();
      }});
      window.addEventListener("mouseup", () => {{ dragging = false; }});

      document.getElementById("fsBtn").onclick = () => {{
        if (!document.fullscreenElement) {{
          wrap.requestFullscreen().catch(() => {{}});
        }} else {{
          document.exitFullscreen().catch(() => {{}});
        }}
      }};

      document.getElementById("dlBtn").onclick = () => {{
        const svg = document.querySelector("#mmd svg");
        if (!svg) return;
        const serializer = new XMLSerializer();
        const svgStr = serializer.serializeToString(svg);
        const blob = new Blob([svgStr], {{ type: "image/svg+xml;charset=utf-8" }});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "project1_pipeline.svg";
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }};

      if (typeof mermaid === "undefined") {{
        document.getElementById("mmd").style.display = "none";
        document.getElementById("fb").style.display = "block";
        return;
      }}
      try {{
        mermaid.initialize({{
          startOnLoad: true,
          securityLevel: "loose",
          theme: "base",
          themeVariables: {{
            primaryColor: "#FFF1E8",
            primaryBorderColor: "#FF5F00",
            primaryTextColor: "#0F172A",
            lineColor: "#94A3B8",
            fontFamily: "Inter, system-ui, -apple-system, sans-serif",
            fontSize: "13px"
          }}
        }});
      }} catch (e) {{
        document.getElementById("mmd").style.display = "none";
        document.getElementById("fb").style.display = "block";
      }}
    }})();
  </script>
</body>
</html>"""
    components.html(page_html, height=height, scrolling=False)
    if not ASSETS_JS.is_file() and dot_fallback:
        with st.expander("Graphviz fallback (offline)", expanded=False):
            st.graphviz_chart(dot_fallback)
