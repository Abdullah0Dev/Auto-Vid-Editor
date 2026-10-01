"""Coordinates the full pipeline. Single entry point."""

from __future__ import annotations

import time
from pathlib import Path

from config import (
    FINAL_DIR,
    MODEL_VISION,
    ENABLE_PREVIEW,
    ENABLE_GRAPHICS,
)

from pipeline import (
    transcriber,
    context_extractor,
    scene_planner,
    query_generator,
    asset_finder,
    vision_judge,
    audio_analyzer,
    clip_builder,
    renderer,
    graphic_pipeline,
)

from utils.logger import log
from utils.llm_client import unload


def run(video_path, bg_music=None, nasheed=None) -> str:
    t0 = time.time()

    FINAL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ============================================================
    # 1. Transcription
    # ============================================================

    log.step(
        1,
        8,
        "Transcribing (mlx-whisper)",
    )

    segments = transcriber.transcribe(
        video_path
    )

    transcript_text = (
        transcriber.to_timestamped_text(
            segments
        )
    )

    video_duration = (
        transcriber.get_video_duration(
            video_path
        )
    )

    # ============================================================
    # 2. Global context
    # ============================================================

    log.step(
        2,
        8,
        "Extracting global context",
    )

    context = (
        context_extractor.extract_context(
            transcript_text
        )
    )

    # ============================================================
    # 3. Scene planning
    #
    # IMPORTANT:
    # The scene planner decides:
    #   image vs graphic
    #   content type
    #   timestamps
    #
    # It does NOT choose the Remotion template.
    # ============================================================

    log.step(
        3,
        8,
        "Planning scenes",
    )

    scenes, moments = scene_planner.plan(
        transcript_text,
        context=context,
        video_duration=video_duration,
    )

    # ============================================================
    # 4. Search-query refinement
    # ============================================================

    log.step(
        4,
        8,
        "Refining search queries",
    )

    scenes = query_generator.generate_queries(
        scenes,
        context,
    )

    # ============================================================
    # 5. Audio + visual asset preparation
    # ============================================================

    log.step(
        5,
        8,
        "Analyzing audio + preparing visual assets",
    )

    audio_analyzer.analyze(
        video_path
    )

    # ============================================================
    # 5a. GRAPHIC PLANNING
    #
    # Do this BEFORE normal image searching.
    #
    # Graphic planner:
    #   scene -> template + props
    #
    # It does NOT decide duration.
    # Duration remains:
    #
    #   scene.end - scene.start
    # ============================================================

    if ENABLE_GRAPHICS:
        log.info(
            "[graphics] Planning Remotion scenes..."
        )

        graphic_pipeline.plan_graphic_scenes(
            scenes,
            context=context,
        )

    # ============================================================
    # 5b. NORMAL IMAGE ASSET SEARCH
    #
    # Only actual image scenes come here.
    #
    # This includes scenes that were originally "graphic" but
    # failed graphic planning and were safely converted to image.
    # ============================================================

    image_scene_count = sum(
        1
        for scene in scenes
        if scene.visual_type == "image"
    )

    image_index = 0

    for scene in scenes:

        if scene.visual_type != "image":
            continue

        image_index += 1

        query_preview = (
            scene.english_query or
            scene.arabic_query or
            scene.text or ""
        )[:60]

        log.info(
            f"[assets {image_index}/{image_scene_count}] "
            f"Scene {scene.id}: {query_preview}"
        )

        try:
            candidates = (
                asset_finder.find_assets(
                    scene
                )
            )

            scene.candidates = candidates

            if (
                candidates
                and not scene.chosen_asset
            ):
                scene.chosen_asset = (
                    candidates[0]
                )

        except Exception as exc:
            log.warn(
                f"Scene {scene.id}: "
                f"asset search failed: {exc}"
            )

            scene.candidates = []

    # ============================================================
    # 5c. RENDER REMOTION GRAPHICS
    #
    # IMPORTANT:
    # Graphic duration is ALWAYS derived from:
    #
    #   scene.end - scene.start
    #
    # Never from an LLM-provided duration.
    #
    # The renderer converts seconds -> frames at GRAPHIC_FPS.
    # ============================================================

    if ENABLE_GRAPHICS:

        log.info(
            "[graphics] Rendering planned graphics..."
        )

        graphic_pipeline.render_graphic_scenes(
            scenes
        )

        # Make rendered graphics visible in the review UI
        # exactly like normal candidate assets.
        for scene in scenes:

            if (
                scene.visual_type != "graphic"
                or not scene.graphic_path
            ):
                continue

            path = Path(
                scene.graphic_path
            )

            if not path.exists():
                log.warn(
                    f"Scene {scene.id}: "
                    f"graphic path disappeared: {path}"
                )
                continue

            scene.candidates = [
                str(path)
            ]

            scene.chosen_asset = str(path)

    # ============================================================
    # 5d. Graphics disabled
    #
    # Convert them to normal image scenes so the pipeline
    # continues safely instead of leaving unresolved graphics.
    # ============================================================

    else:

        for scene in scenes:

            if scene.visual_type != "graphic":
                continue

            log.info(
                f"Scene {scene.id}: "
                f"graphics disabled → image fallback"
            )

            scene.visual_type = "image"

            try:
                candidates = (
                    asset_finder.find_assets(
                        scene
                    )
                )

                scene.candidates = candidates

                if (
                    candidates
                    and not scene.chosen_asset
                ):
                    scene.chosen_asset = (
                        candidates[0]
                    )

            except Exception as exc:
                log.warn(
                    f"Scene {scene.id}: "
                    f"fallback asset search failed: {exc}"
                )

                scene.candidates = []

    # ============================================================
    # 6. Human review
    # ============================================================

    if ENABLE_PREVIEW:

        log.step(
            6,
            8,
            "Human review",
        )

        from pipeline.preview_server import (
            PreviewServer,
        )

        server = PreviewServer(
            scenes,
            context=context,
            original_video=video_path,
        )

        server.start_and_wait()

        # --------------------------------------------------------
        # Vision fallback
        #
        # Only unresolved IMAGE scenes should reach vision_judge.
        #
        # A healthy graphic already has an MP4 chosen_asset.
        # --------------------------------------------------------

        for scene in scenes:

            if scene.visual_type != "image":
                continue

            if (
                scene.chosen_asset
                and Path(
                    scene.chosen_asset
                ).exists()
            ):
                continue

            log.info(
                f"Scene {scene.id}: "
                f"vision fallback..."
            )

            try:
                scene.chosen_asset = (
                    vision_judge.judge(scene)
                )

            finally:
                unload(
                    MODEL_VISION
                )

    # ============================================================
    # 6b. No preview
    # ============================================================

    else:

        for scene in scenes:

            if scene.visual_type != "image":
                continue

            if (
                scene.chosen_asset
                and Path(
                    scene.chosen_asset
                ).exists()
            ):
                continue

            try:
                scene.chosen_asset = (
                    vision_judge.judge(scene)
                )

            finally:
                unload(
                    MODEL_VISION
                )

    # ============================================================
    # 7. Build clips
    # ============================================================

    log.step(
        7,
        8,
        "Building clips",
    )

    clip_paths = (
        clip_builder.build_all(
            video_path,
            scenes,
        )
    )

    # ============================================================
    # 8. Final render
    # ============================================================

    log.step(
        8,
        8,
        "Rendering final video",
    )

    output_path = str(
        FINAL_DIR / "final_video.mp4"
    )

    renderer.render(
        clip_paths,
        video_path,
        output_path,
        moments,
        scenes,
        bg_music,
        nasheed,
    )

    log.ok(
        "Pipeline finished in "
        f"{(time.time() - t0) / 60:.1f} min"
    )

    return output_path