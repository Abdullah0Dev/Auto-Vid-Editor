"""Human-in-the-loop review step.

Runs BEFORE vision judging — the user picks the best candidate for each
scene, or pastes a custom URL/path. Whatever is chosen becomes the
scene's `chosen_asset` and the vision model is skipped for that scene.
"""
import shutil
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

from config import (
    WEB_DIR, SCENE_ASSETS_DIR, PLAN_DIR,
    PREVIEW_PORT, PREVIEW_TIMEOUT_MINUTES, PREVIEW_AUTO_OPEN,
)
from models.types import Scene
from utils.logger import log


_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp",
                 ".mp4", ".mov", ".webm", ".m4v"}


class PreviewServer:
    def __init__(self, scenes: list[Scene], context: dict | None = None,
                 original_video: str | None = None):
        self.scenes = scenes
        self.context = context or {}
        self.original_video = original_video
        self.proceed_event = threading.Event()
        self.app = Flask(__name__, static_folder=None)
        self._setup_routes()

    # --------------------------------------------------------
    def _setup_routes(self):
        app = self.app

        @app.route("/")
        def index():
            html = (WEB_DIR / "preview.html").read_text(encoding="utf-8")
            return Response(html, mimetype="text/html")

        @app.route("/api/state")
        def state():
            return jsonify({
                "scenes": [self._to_dict(s) for s in self.scenes],
                "context": self.context,
                "timeout_seconds": PREVIEW_TIMEOUT_MINUTES * 60,
            })

        @app.route("/api/scene/<int:scene_id>", methods=["POST"])
        def update_scene(scene_id):
            data = request.get_json() or {}
            scene = next((s for s in self.scenes if s.id == scene_id), None)
            if scene is None:
                return jsonify({"error": "scene not found"}), 404

            # Choose one of the pre-downloaded candidates
            if data.get("chosen_asset"):
                path = str(data["chosen_asset"])
                if path not in scene.candidates:
                    return jsonify({"error": "unknown candidate"}), 400
                scene.chosen_asset = path
                log.ok(f"Scene {scene.id}: user picked candidate {Path(path).name}")

            # Replace with URL or local path
            if data.get("asset_url"):
                err = self._replace_asset(scene, str(data["asset_url"]).strip())
                if err:
                    return jsonify({"error": err}), 400

            # ── Ken Burns / importance ────────────────────
            if "ken_burns" in data:
                scene.ken_burns = str(data["ken_burns"])
            if "is_important" in data:
                scene.is_important = bool(data["is_important"])

            # ── Fit mode (cover / contain) ────────────────
            if "fit_mode" in data:
                fm = str(data["fit_mode"])
                if fm in ("contain", "cover"):
                    scene.fit_mode = fm

            # ── Fit offsets (object-position X/Y in 0–100) ─
            if "fit_offset_x" in data or "fit_offset_y" in data:
                try:
                    ox = float(data.get("fit_offset_x",
                                        getattr(scene, "fit_offset_x", 50.0)))
                    oy = float(data.get("fit_offset_y",
                                        getattr(scene, "fit_offset_y", 50.0)))
                except (TypeError, ValueError):
                    return jsonify({"error": "invalid offset"}), 400
                # Clamp so a bad client can't poison the renderer
                scene.fit_offset_x = max(0.0, min(100.0, ox))
                scene.fit_offset_y = max(0.0, min(100.0, oy))

            return jsonify({"ok": True, "scene": self._to_dict(scene)})

        @app.route("/api/proceed", methods=["POST"])
        def proceed():
            self.proceed_event.set()
            return jsonify({"ok": True})

        @app.route("/asset/<int:scene_id>/<path:filename>")
        def serve_asset(scene_id, filename):
            d = SCENE_ASSETS_DIR / f"scene_{scene_id:03d}"
            return send_from_directory(str(d), filename)

        @app.route("/original")
        def serve_original():
            if not self.original_video or not Path(self.original_video).exists():
                return Response("no original configured", status=404)
            d = Path(self.original_video).parent
            return send_from_directory(str(d), Path(self.original_video).name)

    # --------------------------------------------------------
    def _to_dict(self, s: Scene) -> dict:
        return {
            "id": s.id, "start": s.start, "end": s.end,
            "text": s.text, "visual_type": s.visual_type,
            "arabic_query": s.arabic_query, "english_query": s.english_query,
            "audio_note": s.audio_note,
            "is_important": s.is_important, "ken_burns": s.ken_burns,
            "fit_mode": getattr(s, "fit_mode", "contain"),
            "fit_offset_x": getattr(s, "fit_offset_x", 50.0),
            "fit_offset_y": getattr(s, "fit_offset_y", 50.0),
            "chosen_asset": s.chosen_asset, "candidates": s.candidates,
            "chosen_url": self._asset_url(s),
        }

    def _asset_url(self, s: Scene) -> str | None:
        if not s.chosen_asset:
            return None
        p = Path(s.chosen_asset)
        if not p.exists():
            return None
        return f"/asset/{s.id}/{p.name}"

    def _replace_asset(self, scene: Scene, source: str) -> str | None:
        """Return None on success, error string on failure."""
        scene_dir = SCENE_ASSETS_DIR / f"scene_{scene.id:03d}"
        scene_dir.mkdir(parents=True, exist_ok=True)

        # Local path
        if not source.startswith(("http://", "https://")):
            local = Path(source).expanduser()
            if not local.exists():
                return f"المسار غير موجود: {local}"
            dest = scene_dir / f"custom_{local.name}"
            shutil.copy2(local, dest)
            scene.chosen_asset = str(dest)
            if str(dest) not in scene.candidates:
                scene.candidates.append(str(dest))
            log.ok(f"Scene {scene.id}: user added local {local.name}")
            return None

        # Remote URL
        try:
            r = requests.get(source, stream=True, timeout=60, headers={
                "User-Agent": "ArabicVideoEditor/1.0 (local review)"
            })
            r.raise_for_status()
        except requests.RequestException as e:
            return f"فشل التنزيل: {e}"

        ext = Path(urlparse(source).path).suffix.lower()
        if ext not in _ALLOWED_EXTS:
            ctype = r.headers.get("Content-Type", "").lower()
            if "png" in ctype:   ext = ".png"
            elif "webp" in ctype: ext = ".webp"
            elif "mp4" in ctype:  ext = ".mp4"
            elif "webm" in ctype: ext = ".webm"
            else:                 ext = ".jpg"

        dest = scene_dir / f"custom{ext}"
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        if dest.stat().st_size < 1000:
            dest.unlink(missing_ok=True)
            return "الملف صغير جداً"

        scene.chosen_asset = str(dest)
        if str(dest) not in scene.candidates:
            scene.candidates.append(str(dest))
        log.ok(f"Scene {scene.id}: user added URL {source[:60]}")
        return None

    # --------------------------------------------------------
    def start_and_wait(self) -> bool:
        from werkzeug.serving import make_server
        srv = make_server("127.0.0.1", PREVIEW_PORT, self.app, threaded=True)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()

        url = f"http://127.0.0.1:{PREVIEW_PORT}"
        log.ok(f"Preview UI: {url}")
        if PREVIEW_AUTO_OPEN:
            try: webbrowser.open(url)
            except Exception: pass

        timeout_s = PREVIEW_TIMEOUT_MINUTES * 60
        log.info(f"Waiting up to {PREVIEW_TIMEOUT_MINUTES} min for review…")

        got = self.proceed_event.wait(timeout=timeout_s)
        srv.shutdown()

        if got:
            log.ok("User pressed متابعة — continuing pipeline")
        else:
            log.warn(f"Preview timed out — continuing with current state")

        import json
        (PLAN_DIR / "scene_plan.json").write_text(
            json.dumps(
                {"scenes": [vars(s) for s in self.scenes],
                 "important_moments": []},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        return got