"""Human-in-the-loop review step.

Runs BEFORE vision judging — the user picks the best candidate for each
scene, or pastes a custom URL/path. Whatever is chosen becomes the
scene's `chosen_asset` and the vision model is skipped for that scene.

The preview UI also supports creating custom Remotion graphics directly.
"""

import json
import mimetypes
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from config import (
    WEB_DIR,
    SCENE_ASSETS_DIR,
    PLAN_DIR,
    PREVIEW_PORT,
    PREVIEW_TIMEOUT_MINUTES,
    PREVIEW_AUTO_OPEN,
       VECTOR_CLIPS_DIR,
)
from models.types import Scene
from utils.logger import log


# ============================================================
# Asset / graphics configuration
# ============================================================

_ALLOWED_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".mp4",
    ".mov",
    ".webm",
    ".m4v",
}

_VIDEO_EXTS = {
    ".mp4",
    ".mov",
    ".webm",
    ".m4v",
}

_IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

_GRAPHICS_DIR = Path("cache/graphics").resolve()
_THUMBNAILS_DIR = (_GRAPHICS_DIR / "_thumbnails").resolve()

_GRAPHICS_DIR.mkdir(parents=True, exist_ok=True)
_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Graphic rendering jobs
# ============================================================

_GRAPHIC_JOBS: dict[str, dict] = {}
_GRAPHIC_JOBS_LOCK = threading.Lock()

# Keep the in-memory job table from growing forever.
_JOB_MAX_AGE_SECONDS = 60 * 60


class PreviewServer:
    def __init__(
        self,
        scenes: list[Scene],
        context: dict | None = None,
        original_video: str | None = None,
    ):
        self.scenes = scenes
        self.context = context or {}
        self.original_video = original_video
        self.proceed_event = threading.Event()

        self.app = Flask(__name__, static_folder=None)

        self._setup_routes()

    # ========================================================
    # Routes
    # ========================================================

    def _setup_routes(self):
        app = self.app

        # ----------------------------------------------------
        # Main preview page
        # ----------------------------------------------------

        @app.route("/")
        def index():
            html = (WEB_DIR / "preview.html").read_text(
                encoding="utf-8"
            )
            return Response(html, mimetype="text/html")

        # ----------------------------------------------------
        # State
        # ----------------------------------------------------

        @app.route("/api/state")
        def state():
            return jsonify({
                "scenes": [
                    self._to_dict(s)
                    for s in self.scenes
                ],
                "context": self.context,
                "timeout_seconds": PREVIEW_TIMEOUT_MINUTES * 60,
            })

        # ----------------------------------------------------
        # Graphic template metadata
        # ----------------------------------------------------

        @app.route("/api/graphic/templates")
        def graphic_templates():
            """
            Return the templates available to the preview UI.

            The actual Remotion registry lives in TypeScript, so this
            endpoint intentionally keeps the Python side lightweight.

            `fields` can be expanded later with richer per-template
            metadata without changing the frontend API.
            """

            templates = [
                {
                    "id": "poem",
                    "label": "قصيدة",
                    "fields": self._template_fields("poem"),
                },
                {
                    "id": "hadith",
                    "label": "حديث",
                    "fields": self._template_fields("hadith"),
                },
                {
                    "id": "quran",
                    "label": "آية قرآنية",
                    "fields": self._template_fields("quran"),
                },
                {
                    "id": "quote",
                    "label": "اقتباس",
                    "fields": self._template_fields("quote"),
                },
                {
                    "id": "battle",
                    "label": "معركة",
                    "fields": self._template_fields("battle"),
                },
                {
                    "id": "map",
                    "label": "خريطة",
                    "fields": self._template_fields("map"),
                },
                {
                    "id": "audio_visualizer",
                    "label": "موجّه صوتي",
                    "fields": self._template_fields(
                        "audio_visualizer"
                    ),
                },
                {
                    "id": "person_card",
                    "label": "بطاقة شخصية",
                    "fields": self._template_fields(
                        "person_card"
                    ),
                },
                {
                    "id": "ken_burns",
                    "label": "Ken Burns",
                    "fields": self._template_fields(
                        "ken_burns"
                    ),
                },
                {
                    "id": "counter",
                    "label": "عداد",
                    "fields": self._template_fields(
                        "counter"
                    ),
                },
                {
                    "id": "karaoke",
                    "label": "كاريوكي",
                    "fields": self._template_fields(
                        "karaoke"
                    ),
                },
            ]

            return jsonify({
                "templates": templates,
            })

        # ----------------------------------------------------
        # Choose / update scene
        # ----------------------------------------------------

        @app.route(
            "/api/scene/<int:scene_id>",
            methods=["POST"],
        )
        def update_scene(scene_id):
            data = request.get_json() or {}

            scene = next(
                (
                    s
                    for s in self.scenes
                    if s.id == scene_id
                ),
                None,
            )

            if scene is None:
                return jsonify({
                    "error": "scene not found"
                }), 404

            # ----------------------------------------------
            # Choose one of the candidates
            # ----------------------------------------------

            if data.get("chosen_asset"):
                path = str(data["chosen_asset"])

                if path not in scene.candidates:
                    return jsonify({
                        "error": "unknown candidate"
                    }), 400

                scene.chosen_asset = path

                log.ok(
                    f"Scene {scene.id}: "
                    f"user picked candidate "
                    f"{Path(path).name}"
                )

            # ----------------------------------------------
            # Replace with URL or local path
            # ----------------------------------------------

            if data.get("asset_url"):
                err = self._replace_asset(
                    scene,
                    str(data["asset_url"]).strip(),
                )

                if err:
                    return jsonify({
                        "error": err
                    }), 400

            # ----------------------------------------------
            # Ken Burns / importance
            # ----------------------------------------------

            if "ken_burns" in data:
                scene.ken_burns = str(
                    data["ken_burns"]
                )

            if "is_important" in data:
                scene.is_important = bool(
                    data["is_important"]
                )

            # ----------------------------------------------
            # Fit mode
            # ----------------------------------------------

            if "fit_mode" in data:
                fm = str(data["fit_mode"])

                if fm in ("contain", "cover"):
                    scene.fit_mode = fm
                    
            # ----------------------------------------------
            # B-roll volume
            # ----------------------------------------------

            if "volume" in data:
                try:
                    volume = float(data["volume"])
                except (TypeError, ValueError):
                    return jsonify({
                        "error": "invalid volume"
                    }), 400

                scene.volume = max(
                    0.0,
                    min(1.0, volume),
                )
            # ----------------------------------------------
            # Fit offsets
            # ----------------------------------------------

            if (
                "fit_offset_x" in data
                or "fit_offset_y" in data
            ):
                try:
                    ox = float(
                        data.get(
                            "fit_offset_x",
                            getattr(
                                scene,
                                "fit_offset_x",
                                50.0,
                            ),
                        )
                    )

                    oy = float(
                        data.get(
                            "fit_offset_y",
                            getattr(
                                scene,
                                "fit_offset_y",
                                50.0,
                            ),
                        )
                    )

                except (TypeError, ValueError):
                    return jsonify({
                        "error": "invalid offset"
                    }), 400

                scene.fit_offset_x = max(
                    0.0,
                    min(100.0, ox),
                )

                scene.fit_offset_y = max(
                    0.0,
                    min(100.0, oy),
                )

            return jsonify({
                "ok": True,
                "scene": self._to_dict(scene),
            })

        # ----------------------------------------------------
        # Create custom graphic
        # ----------------------------------------------------

        @app.route(
            "/api/scene/<int:scene_id>/create-graphic",
            methods=["POST"],
        )
        def create_graphic(scene_id):
            scene = next(
                (
                    s
                    for s in self.scenes
                    if s.id == scene_id
                ),
                None,
            )

            if scene is None:
                return jsonify({
                    "error": "scene not found"
                }), 404

            data = request.get_json() or {}

            template = str(
                data.get("template", "")
            ).strip()

            props = data.get("props")

            if not template:
                return jsonify({
                    "error": "template is required"
                }), 400

            if props is None:
                props = {}

            if not isinstance(props, dict):
                return jsonify({
                    "error": "props must be an object"
                }), 400

            # Validate template against the actual renderer
            # rather than blindly accepting arbitrary strings.
            try:
                self._validate_graphic_template(
                    template
                )
            except ValueError as e:
                return jsonify({
                    "error": str(e)
                }), 400

            job_id = uuid.uuid4().hex

            self._set_graphic_job(
                job_id,
                {
                    "id": job_id,
                    "scene_id": scene.id,
                    "template": template,
                    "status": "queued",
                    "progress": 0,
                    "message": "جارٍ تجهيز المشهد…",
                    "created_at": time.time(),
                    "updated_at": time.time(),
                },
            )

            thread = threading.Thread(
                target=self._run_graphic_job,
                args=(
                    job_id,
                    scene.id,
                    template,
                    props,
                ),
                daemon=True,
                name=f"graphic-render-{job_id[:8]}",
            )

            thread.start()

            return jsonify({
                "ok": True,
                "job_id": job_id,
            })

        # ----------------------------------------------------
        # Graphic job status
        # ----------------------------------------------------

        @app.route(
            "/api/graphic/jobs/<job_id>"
        )
        def graphic_job_status(job_id):
            job = self._get_graphic_job(job_id)

            if job is None:
                return jsonify({
                    "error": "job not found"
                }), 404

            # Include the latest scene once rendering has
            # completed so the frontend can immediately
            # refresh the candidate list.
            payload = dict(job)

            scene_id = job.get("scene_id")

            if scene_id is not None:
                scene = next(
                    (
                        s
                        for s in self.scenes
                        if s.id == scene_id
                    ),
                    None,
                )

                if scene is not None:
                    payload["scene"] = self._to_dict(
                        scene
                    )

            return jsonify(payload)

        # ----------------------------------------------------
        # Rerender existing graphic
        # ----------------------------------------------------

        @app.route(
            "/api/scene/<int:scene_id>/rerender-graphic",
            methods=["POST"],
        )
        def rerender_graphic(scene_id):
            from pipeline import (
                graphic_planner,
                graphic_renderer,
            )

            scene = next(
                (
                    s
                    for s in self.scenes
                    if s.id == scene_id
                ),
                None,
            )

            if scene is None:
                return jsonify({
                    "error": "scene not found"
                }), 404

            data = request.get_json() or {}
            plan = data.get("plan")

            # Keep your existing behavior:
            # supplied plan is used when it is a valid
            # map/graphic plan; otherwise planner creates one.
            if not plan or not plan.get("template"):
                plan = graphic_planner.plan_graphic(
                    scene,
                    self.context,
                )

            if not plan:
                return jsonify({
                    "error": "no plan available"
                }), 400

            template = plan.get("template")

            try:
                self._validate_graphic_template(
                    template
                )
            except ValueError as e:
                return jsonify({
                    "error": str(e)
                }), 400

            dur = scene.end - scene.start

            try:
                path = graphic_renderer.render_graphic(
                    template=template,
                    props=plan.get("props", {}),
                    duration_seconds=dur,
                )

            except Exception as e:
                log.error(
                    f"Graphic rerender failed "
                    f"for scene {scene.id}: {e}"
                )

                return jsonify({
                    "error": f"render failed: {e}"
                }), 500

            path = Path(path).resolve()

            scene.graphic_template = template
            scene.graphic_props = plan.get(
                "props",
                {},
            )
            scene.graphic_path = str(path)

            # IMPORTANT:
            # Don't automatically choose the rerendered
            # graphic. Make it available as a candidate.
            self._add_candidate(
                scene,
                path,
            )

            return jsonify({
                "ok": True,
                "scene": self._to_dict(scene),
            })

        # ----------------------------------------------------
        # Asset serving
        # ----------------------------------------------------

        @app.route(
            "/asset/<int:scene_id>/<path:filename>"
        )
        def serve_asset(scene_id, filename):
            path = self._find_scene_asset(
                scene_id,
                filename,
            )

            if path is None:
                return Response(
                    "asset not found",
                    status=404,
                )

            return send_file(
                path,
                conditional=True,
            )

        # ----------------------------------------------------
        # Video thumbnail
        # ----------------------------------------------------

        @app.route(
            "/thumb/<int:scene_id>/<path:filename>"
        )
        def serve_thumbnail(scene_id, filename):
            path = self._find_scene_asset(
                scene_id,
                filename,
            )

            if path is None:
                return Response(
                    "asset not found",
                    status=404,
                )

            # Images don't need a generated thumbnail.
            if path.suffix.lower() not in _VIDEO_EXTS:
                return send_file(
                    path,
                    conditional=True,
                )

            try:
                thumb = self._get_video_thumbnail(
                    path
                )
            except Exception as e:
                log.warn(
                    f"Thumbnail generation failed "
                    f"for {path.name}: {e}"
                )

                return Response(
                    "thumbnail generation failed",
                    status=500,
                )

            return send_file(
                thumb,
                mimetype="image/jpeg",
                conditional=True,
            )

        # ----------------------------------------------------
        # Proceed
        # ----------------------------------------------------

        @app.route(
            "/api/proceed",
            methods=["POST"],
        )
        def proceed():
            self.proceed_event.set()

            return jsonify({
                "ok": True
            })

        # ----------------------------------------------------
        # Original source video
        # ----------------------------------------------------

        @app.route("/original")
        def serve_original():
            if (
                not self.original_video
                or not Path(
                    self.original_video
                ).exists()
            ):
                return Response(
                    "no original configured",
                    status=404,
                )

            d = Path(
                self.original_video
            ).parent

            return send_from_directory(
                str(d),
                Path(
                    self.original_video
                ).name,
            )

    # ========================================================
    # Graphic jobs
    # ========================================================

    def _run_graphic_job(
        self,
        job_id: str,
        scene_id: int,
        template: str,
        props: dict,
    ):
        from pipeline import graphic_renderer

        try:
            self._update_graphic_job(
                job_id,
                status="rendering",
                progress=5,
                message="جارٍ بدء الإخراج…",
            )

            scene = next(
                (
                    s
                    for s in self.scenes
                    if s.id == scene_id
                ),
                None,
            )

            if scene is None:
                raise RuntimeError(
                    "scene not found"
                )

            duration_seconds = (
                scene.end - scene.start
            )

            self._update_graphic_job(
                job_id,
                progress=10,
                message="جارٍ إخراج الفيديو…",
            )

            path = graphic_renderer.render_graphic(
                template=template,
                props=props,
                duration_seconds=duration_seconds,
            )

            path = Path(path).resolve()

            if not path.exists():
                raise RuntimeError(
                    "renderer returned a missing file"
                )

            if path.stat().st_size <= 0:
                raise RuntimeError(
                    "renderer produced an empty file"
                )

            # ----------------------------------------------
            # Add generated MP4 as a candidate.
            #
            # Do NOT choose it automatically.
            # ----------------------------------------------

            self._add_candidate(
                scene,
                path,
            )

            scene.graphic_template = template
            scene.graphic_props = props
            scene.graphic_path = str(path)

            self._update_graphic_job(
                job_id,
                status="done",
                progress=100,
                message=(
                    "اكتمل الإخراج — "
                    "اختر الفيديو من خيارات المشهد."
                ),
                output=str(path),
            )

            log.ok(
                f"Scene {scene.id}: "
                f"custom graphic created "
                f"{path.name}"
            )

        except Exception as e:
            log.error(
                f"Custom graphic job {job_id} failed: {e}"
            )

            self._update_graphic_job(
                job_id,
                status="error",
                progress=0,
                message=str(e),
                error=str(e),
            )

    def _set_graphic_job(
        self,
        job_id: str,
        data: dict,
    ):
        with _GRAPHIC_JOBS_LOCK:
            _GRAPHIC_JOBS[job_id] = data

            self._cleanup_old_jobs_locked()

    def _get_graphic_job(
        self,
        job_id: str,
    ) -> dict | None:
        with _GRAPHIC_JOBS_LOCK:
            job = _GRAPHIC_JOBS.get(job_id)

            if job is None:
                return None

            return dict(job)

    def _update_graphic_job(
        self,
        job_id: str,
        **updates,
    ):
        with _GRAPHIC_JOBS_LOCK:
            job = _GRAPHIC_JOBS.get(job_id)

            if job is None:
                return

            job.update(updates)
            job["updated_at"] = time.time()

    @staticmethod
    def _cleanup_old_jobs_locked():
        now = time.time()

        dead = []

        for job_id, job in _GRAPHIC_JOBS.items():
            updated = job.get(
                "updated_at",
                job.get("created_at", now),
            )

            if (
                now - updated
                > _JOB_MAX_AGE_SECONDS
            ):
                dead.append(job_id)

        for job_id in dead:
            _GRAPHIC_JOBS.pop(
                job_id,
                None,
            )

    # ========================================================
    # Graphic template validation
    # ========================================================

    @staticmethod
    def _validate_graphic_template(
        template: str,
    ):
        """
        Validate against the templates that the current
        Remotion registry exposes.

        Keep this list aligned with remotion/src/registry.ts.
        """

        allowed = {
            "poem",
            "hadith",
            "quran",
            "quote",
            "battle",
            "map",
            "audio_visualizer",
            "person_card",
            "ken_burns",
            "counter",
            "karaoke",
        }

        # Backwards compatibility with older planner output.
        if template == "islamic_map":
            template = "map"

        if template not in allowed:
            raise ValueError(
                f"unsupported graphic template: {template}"
            )

    @staticmethod
    def _template_fields(
        template: str,
    ) -> list[dict]:
        """
        UI schema for editable Remotion template props.

        Only expose props that the user can meaningfully edit.
        Runtime/generated props such as fps, duration, timing,
        reading duration, animation frame timings, and source paths
        remain controlled by the renderer/planner.
        """

        common = {

            # ====================================================
            # POEM
            # ====================================================

            "poem": [
                {
                    "key": "poemLines",
                    "label": "سطور القصيدة",
                    "type": "json",
                    "value": [],
                    "help": (
                        'مثال: [{"text1":"الشطر الأول",'
                        '"text2":"الشطر الثاني"}]'
                    ),
                },
                {
                    "key": "footerLabel",
                    "label": "النص السفلي",
                    "type": "text",
                    "value": "",
                },
            ],

            # ====================================================
            # HADITH
            # ====================================================

            "hadith": [
                {
                    "key": "topLabel",
                    "label": "العنوان العلوي",
                    "type": "text",
                    "value": "حَـدِيـث",
                },
                {
                    "key": "isnad",
                    "label": "السند",
                    "type": "textarea",
                    "value": "",
                },
                {
                    "key": "matnPlain",
                    "label": "نص الحديث",
                    "type": "textarea",
                    "value": "",
                },
                {
                    "key": "source",
                    "label": "المصدر",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "wrapInGuillemets",
                    "label": "إحاطة النص بعلامات الاقتباس",
                    "type": "checkbox",
                    "value": True,
                },
            ],

            # ====================================================
            # QURAN
            # ====================================================

            "quran": [
                {
                    "key": "basmala",
                    "label": "البسملة",
                    "type": "text",
                    "value": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                },
                {
                    "key": "surahName",
                    "label": "اسم السورة",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "verses",
                    "label": "الآيات",
                    "type": "json",
                    "value": [],
                    "help": (
                        'مثال: [{"text":"نص الآية","number":1}]'
                    ),
                },
            ],

            # ====================================================
            # QUOTE
            # ====================================================

            "quote": [
                {
                    "key": "topLabel",
                    "label": "العنوان العلوي",
                    "type": "text",
                    "value": "اقْـتِـبَـاس",
                },
                {
                    "key": "speaker",
                    "label": "القائل",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "quotePlain",
                    "label": "نص الاقتباس",
                    "type": "textarea",
                    "value": "",
                },
                {
                    "key": "source",
                    "label": "المصدر",
                    "type": "text",
                    "value": "",
                },
            ],

            # ====================================================
            # BATTLE
            # ====================================================

            "battle": [
                {
                    "key": "hijriDate",
                    "label": "التاريخ الهجري",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "miladiDate",
                    "label": "التاريخ الميلادي",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "battleName",
                    "label": "اسم المعركة",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "side1",
                    "label": "الطرف الأول",
                    "type": "json",
                    "value": {
                        "name": "",
                        "detail": "",
                    },
                    "help": (
                        'مثال: {"name":"الطرف الأول",'
                        '"detail":"وصف مختصر"}'
                    ),
                },
                {
                    "key": "side2",
                    "label": "الطرف الثاني",
                    "type": "json",
                    "value": {
                        "name": "",
                        "detail": "",
                    },
                    "help": (
                        'مثال: {"name":"الطرف الثاني",'
                        '"detail":"وصف مختصر"}'
                    ),
                },
                {
                    "key": "outcome",
                    "label": "النتيجة",
                    "type": "textarea",
                    "value": "",
                },
                {
                    "key": "source",
                    "label": "المصدر",
                    "type": "text",
                    "value": "",
                },
            ],

            # ====================================================
            # MAP
            # ====================================================

            "map": [
                {
                    "key": "title",
                    "label": "عنوان الخريطة",
                    "type": "text",
                    "value": "دِيَارُ الإِسْلَام",
                },
                {
                    "key": "subtitle",
                    "label": "العنوان الفرعي",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "footer",
                    "label": "النص السفلي",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "cities",
                    "label": "المدن",
                    "type": "json",
                    "value": [],
                    "help": (
                        'مثال: ["baghdad","damascus","cairo"]'
                    ),
                },
                {
                    "key": "spotlight",
                    "label": "المدينة المميزة",
                    "type": "json",
                    "value": None,
                    "help": (
                        'مثال: {"cityId":"baghdad",'
                        '"label":"هُنَا"}'
                    ),
                },
                {
                    "key": "journey",
                    "label": "مسار الرحلة",
                    "type": "json",
                    "value": None,
                    "help": (
                        'مثال: {"path":["baghdad","damascus"],'
                        '"label":"الرحلة"}'
                    ),
                },
            ],

            # ====================================================
            # PERSON CARD
            # ====================================================

            "person_card": [
                {
                    "key": "name",
                    "label": "اسم الشخصية",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "honorific",
                    "label": "اللقب / الترضية",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "title",
                    "label": "المنصب / الوصف",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "birthYear",
                    "label": "سنة الميلاد",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "deathYear",
                    "label": "سنة الوفاة",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "birthPlace",
                    "label": "مكان الميلاد",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "deathPlace",
                    "label": "مكان الوفاة",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "footerLabel",
                    "label": "النص السفلي",
                    "type": "text",
                    "value": "",
                },
            ],

            # ====================================================
            # COUNTER
            # ====================================================

            "counter": [
                {
                    "key": "value",
                    "label": "الرقم",
                    "type": "number",
                    "value": 0,
                },
                {
                    "key": "prefix",
                    "label": "قبل الرقم",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "suffix",
                    "label": "بعد الرقم",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "label",
                    "label": "العنوان",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "subLabel",
                    "label": "الوصف الفرعي",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "topLabel",
                    "label": "العنوان العلوي",
                    "type": "text",
                    "value": "",
                },
                {
                    "key": "numberFormat",
                    "label": "تنسيق الأرقام",
                    "type": "select",
                    "value": "arabic",
                    "options": [
                        {
                            "value": "arabic",
                            "label": "عربي ١٢٣",
                        },
                        {
                            "value": "western",
                            "label": "غربي 123",
                        },
                    ],
                },
                {
                    "key": "thousandsSeparator",
                    "label": "فاصل الآلاف",
                    "type": "select",
                    "value": "٬",
                    "options": [
                        {
                            "value": "٬",
                            "label": "٬",
                        },
                        {
                            "value": ",",
                            "label": ",",
                        },
                        {
                            "value": "",
                            "label": "بدون فاصل",
                        },
                    ],
                },
                {
                    "key": "curve",
                    "label": "حركة العداد",
                    "type": "select",
                    "value": "easeOut",
                    "options": [
                        {
                            "value": "linear",
                            "label": "Linear",
                        },
                        {
                            "value": "easeOut",
                            "label": "Ease Out",
                        },
                        {
                            "value": "easeInOut",
                            "label": "Ease In Out",
                        },
                    ],
                },
            ],

            # ====================================================
            # KARAOKE
            # ====================================================

            "karaoke": [
                {
                    "key": "background",
                    "label": "الخلفية",
                    "type": "text",
                    "value": "poem-bg.jpeg",
                },
                {
                    "key": "theme",
                    "label": "الثيم",
                    "type": "select",
                    "value": "parchment",
                    "options": [
                        {
                            "value": "parchment",
                            "label": "Parchment",
                        },
                        {
                            "value": "crimson",
                            "label": "Crimson",
                        },
                        {
                            "value": "andalusian",
                            "label": "Andalusian",
                        },
                        {
                            "value": "night",
                            "label": "Night",
                        },
                    ],
                },
                {
                    "key": "style",
                    "label": "نمط ظهور الكلمات",
                    "type": "select",
                    "value": "pop",
                    "options": [
                        {
                            "value": "underline",
                            "label": "Underline",
                        },
                        {
                            "value": "rise",
                            "label": "Rise",
                        },
                        {
                            "value": "pop",
                            "label": "Pop",
                        },
                        {
                            "value": "blurFocus",
                            "label": "Blur Focus",
                        },
                        {
                            "value": "dualTone",
                            "label": "Dual Tone",
                        },
                        {
                            "value": "wave",
                            "label": "Wave",
                        },
                    ],
                },
                {
                    "key": "text",
                    "label": "النص",
                    "type": "textarea",
                    "value": "",
                },
                {
                    "key": "header",
                    "label": "العنوان",
                    "type": "text",
                    "value": "",
                },
            ],

            # ====================================================
            # AUDIO VISUALIZER
            # ====================================================

            "audio_visualizer": [
                {
                    "key": "background",
                    "label": "الخلفية",
                    "type": "text",
                    "value": "poem-bg.jpeg",
                },
                {
                    "key": "mode",
                    "label": "نمط العرض",
                    "type": "select",
                    "value": "waveform",
                    "options": [
                        {
                            "value": "spectrum",
                            "label": "Spectrum",
                        },
                        {
                            "value": "waveform",
                            "label": "Waveform",
                        },
                    ],
                },
                {
                    "key": "title",
                    "label": "عنوان العرض",
                    "type": "json",
                    "value": None,
                    "help": (
                        'مثال: {"speaker":"اسم المتحدث",'
                        '"subtitle":"وصف"}'
                    ),
                },
            ],

            # ====================================================
            # KEN BURNS
            # ====================================================

            "ken_burns": [
                {
                    "key": "motion",
                    "label": "حركة الصورة",
                    "type": "select",
                    "value": "zoom-in",
                    "options": [
                        {
                            "value": "zoom-in",
                            "label": "Zoom In",
                        },
                        {
                            "value": "zoom-out",
                            "label": "Zoom Out",
                        },
                        {
                            "value": "pan-left",
                            "label": "Pan Left",
                        },
                        {
                            "value": "pan-right",
                            "label": "Pan Right",
                        },
                        {
                            "value": "pan-up",
                            "label": "Pan Up",
                        },
                        {
                            "value": "pan-down",
                            "label": "Pan Down",
                        },
                        {
                            "value": "diagonal-tl",
                            "label": "Diagonal ↖",
                        },
                        {
                            "value": "diagonal-tr",
                            "label": "Diagonal ↗",
                        },
                        {
                            "value": "diagonal-bl",
                            "label": "Diagonal ↙",
                        },
                        {
                            "value": "diagonal-br",
                            "label": "Diagonal ↘",
                        },
                    ],
                },
                {
                    "key": "caption",
                    "label": "النص فوق الصورة",
                    "type": "json",
                    "value": None,
                    "help": (
                        'مثال: {"line1":"السطر الأول",'
                        '"line2":"السطر الثاني"}'
                    ),
                },
                {
                    "key": "source",
                    "label": "المصدر",
                    "type": "text",
                    "value": "",
                },
            ],
        }

        return common.get(
            template,
            [],
        )
    # ========================================================
    # Asset helpers
    # ========================================================

    def _add_candidate(
        self,
        scene: Scene,
        path: Path,
    ):
        path = Path(path).resolve()
        value = str(path)

        if value not in scene.candidates:
            scene.candidates.append(value)

    def _find_scene_asset(
        self,
        scene_id: int,
        filename: str,
    ) -> Path | None:
        """
        Resolve an asset from one of the trusted asset locations:

        1. Current scene assets
        2. Local shared B-roll library: assets/clips
        3. Remotion graphics cache

        The browser can only request a filename, never an arbitrary
        filesystem path.
        """

        filename = Path(filename).name

        if not filename:
            return None

        # ----------------------------------------------
        # 1. Scene assets
        # ----------------------------------------------

        scene_dir = (
            SCENE_ASSETS_DIR
            / f"scene_{scene_id:03d}"
        ).resolve()

        candidate = (
            scene_dir / filename
        ).resolve()

        if (
            self._is_inside(
                candidate,
                scene_dir,
            )
            and candidate.is_file()
        ):
            return candidate

        # ----------------------------------------------
        # 2. Shared/local B-roll library
        # ----------------------------------------------

        clips_dir = Path(
            VECTOR_CLIPS_DIR
        ).resolve()

        clip = (
            clips_dir / filename
        ).resolve()

        if (
            self._is_inside(
                clip,
                clips_dir,
            )
            and clip.is_file()
        ):
            return clip

        # ----------------------------------------------
        # 3. Remotion graphics
        # ----------------------------------------------

        graphic = (
            _GRAPHICS_DIR / filename
        ).resolve()

        if (
            self._is_inside(
                graphic,
                _GRAPHICS_DIR,
            )
            and graphic.is_file()
        ):
            return graphic

        return None
    @staticmethod
    def _is_inside(
        path: Path,
        root: Path,
    ) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    # ========================================================
    # Video thumbnails
    # ========================================================

    @staticmethod
    def _get_video_thumbnail(
        video_path: Path,
    ) -> Path:
        """
        Extract and cache the first video frame.

        The thumbnail filename incorporates the source path,
        modification time and size, so a changed video gets
        a new thumbnail automatically.
        """

        import hashlib

        stat = video_path.stat()

        cache_key = (
            f"{video_path.resolve()}:"
            f"{stat.st_mtime_ns}:"
            f"{stat.st_size}"
        )

        digest = hashlib.sha256(
            cache_key.encode("utf-8")
        ).hexdigest()

        thumb = (
            _THUMBNAILS_DIR
            / f"{digest}.jpg"
        )

        if thumb.exists() and thumb.stat().st_size:
            return thumb

        tmp = thumb.with_suffix(".tmp.jpg")

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-2",
            "-q:v",
            "2",
            str(tmp),
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )

            if (
                not tmp.exists()
                or tmp.stat().st_size == 0
            ):
                raise RuntimeError(
                    "ffmpeg produced no thumbnail"
                )

            tmp.replace(thumb)

            return thumb

        except FileNotFoundError:
            tmp.unlink(missing_ok=True)

            raise RuntimeError(
                "ffmpeg was not found. "
                "Make sure ffmpeg is installed "
                "and available on PATH."
            )

        except subprocess.CalledProcessError as e:
            tmp.unlink(missing_ok=True)

            raise RuntimeError(
                e.stderr.strip()
                or "ffmpeg failed"
            )

        except subprocess.TimeoutExpired:
            tmp.unlink(missing_ok=True)

            raise RuntimeError(
                "thumbnail generation timed out"
            )

    # ========================================================
    # Serialization
    # ========================================================

    def _to_dict(
        self,
        s: Scene,
    ) -> dict:
        return {
            "id": s.id,
            "start": s.start,
            "end": s.end,
            "text": s.text,
            "visual_type": s.visual_type,
            "arabic_query": s.arabic_query,
            "english_query": s.english_query,
            "audio_note": s.audio_note,
            "is_important": s.is_important,
            "ken_burns": s.ken_burns,
            "volume": float(
            max(
                0.0,
                min(
                    1.0,
                    getattr(s, "volume", 1.0),
                ),
            )
        ),

            "fit_mode": getattr(
                s,
                "fit_mode",
                "contain",
            ),

            "fit_offset_x": getattr(
                s,
                "fit_offset_x",
                50.0,
            ),

            "fit_offset_y": getattr(
                s,
                "fit_offset_y",
                50.0,
            ),

            "chosen_asset": s.chosen_asset,
            "candidates": s.candidates,

            "chosen_url": self._asset_url(s),

            "graphic_template": s.graphic_template,
            "graphic_props": s.graphic_props,

            "is_graphic": (
                s.visual_type == "graphic"
            ),
        }

    def _asset_url(
        self,
        s: Scene,
    ) -> str | None:
        if not s.chosen_asset:
            return None

        p = Path(
            s.chosen_asset
        )

        if not p.exists():
            return None

        return (
            f"/asset/{s.id}/"
            f"{p.name}"
        )

    # ========================================================
    # Custom URL / local asset
    # ========================================================

    def _replace_asset(
        self,
        scene: Scene,
        source: str,
    ) -> str | None:
        """Return None on success, error string on failure."""

        scene_dir = (
            SCENE_ASSETS_DIR
            / f"scene_{scene.id:03d}"
        )

        scene_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # Local path
        # ----------------------------------------------------

        if not source.startswith(
            ("http://", "https://")
        ):
            local = Path(
                source
            ).expanduser()

            if not local.exists():
                return (
                    f"المسار غير موجود: {local}"
                )

            dest = (
                scene_dir
                / f"custom_{local.name}"
            )

            shutil.copy2(
                local,
                dest,
            )

            scene.chosen_asset = str(dest)

            self._add_candidate(
                scene,
                dest,
            )

            log.ok(
                f"Scene {scene.id}: "
                f"user added local "
                f"{local.name}"
            )

            return None

        # ----------------------------------------------------
        # Remote URL
        # ----------------------------------------------------

        try:
            r = requests.get(
                source,
                stream=True,
                timeout=60,
                headers={
                    "User-Agent":
                        "ArabicVideoEditor/1.0 "
                        "(local review)"
                },
            )

            r.raise_for_status()

        except requests.RequestException as e:
            return f"فشل التنزيل: {e}"

        ext = Path(
            urlparse(source).path
        ).suffix.lower()

        if ext not in _ALLOWED_EXTS:
            ctype = (
                r.headers
                .get("Content-Type", "")
                .lower()
            )

            if "png" in ctype:
                ext = ".png"
            elif "webp" in ctype:
                ext = ".webp"
            elif "mp4" in ctype:
                ext = ".mp4"
            elif "webm" in ctype:
                ext = ".webm"
            else:
                ext = ".jpg"

        dest = (
            scene_dir
            / f"custom{ext}"
        )

        with open(dest, "wb") as f:
            for chunk in r.iter_content(
                8192
            ):
                f.write(chunk)

        if dest.stat().st_size < 1000:
            dest.unlink(
                missing_ok=True
            )

            return "الملف صغير جداً"

        scene.chosen_asset = str(dest)

        self._add_candidate(
            scene,
            dest,
        )

        log.ok(
            f"Scene {scene.id}: "
            f"user added URL "
            f"{source[:60]}"
        )

        return None

    # ========================================================
    # Server lifecycle
    # ========================================================

    def start_and_wait(self) -> bool:
        from werkzeug.serving import make_server

        srv = make_server(
            "127.0.0.1",
            PREVIEW_PORT,
            self.app,
            threaded=True,
        )

        t = threading.Thread(
            target=srv.serve_forever,
            daemon=True,
        )

        t.start()

        url = (
            f"http://127.0.0.1:"
            f"{PREVIEW_PORT}"
        )

        log.ok(
            f"Preview UI: {url}"
        )

        if PREVIEW_AUTO_OPEN:
            try:
                webbrowser.open(url)
            except Exception:
                pass

        timeout_s = (
            PREVIEW_TIMEOUT_MINUTES
            * 60
        )

        log.info(
            f"Waiting up to "
            f"{PREVIEW_TIMEOUT_MINUTES} min "
            f"for review…"
        )

        got = self.proceed_event.wait(
            timeout=timeout_s
        )

        srv.shutdown()

        if got:
            log.ok(
                "User pressed متابعة — "
                "continuing pipeline"
            )
        else:
            log.warn(
                "Preview timed out — "
                "continuing with current state"
            )

        (
            PLAN_DIR
            / "scene_plan.json"
        ).write_text(
            json.dumps(
                {
                    "scenes": [
                        vars(s)
                        for s in self.scenes
                    ],
                    "important_moments": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return got