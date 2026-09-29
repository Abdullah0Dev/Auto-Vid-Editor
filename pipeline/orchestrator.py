"""Coordinates the full pipeline. Single entry point."""
import time
from pathlib import Path

from config import FINAL_DIR, MODEL_VISION, ENABLE_PREVIEW
from pipeline import (
    transcriber, context_extractor, scene_planner, query_generator,
    asset_finder, vision_judge, audio_analyzer, clip_builder, renderer,
)
from utils.logger import log
from utils.ollama_client import unload


TOTAL_STEPS = 7


def run(video_path, bg_music=None, nasheed=None) -> str:
    t0 = time.time()
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    log.step(1, 8, "Transcribing (mlx-whisper)")
    segments = transcriber.transcribe(video_path)
    transcript_text = transcriber.to_timestamped_text(segments)
    # Get the true video duration once
    video_duration = transcriber.get_video_duration(video_path)

    log.step(2, 8, "Extracting global context")
    context = context_extractor.extract_context(transcript_text)

    log.step(3, 8, "Planning scenes")
    scenes, moments = scene_planner.plan(transcript_text, context=context, video_duration=video_duration)

    log.step(4, 8, "Refining search queries")
    scenes = query_generator.generate_queries(scenes, context)

    log.step(5, 8, "Analyzing audio + searching assets")
    audio_analyzer.analyze(video_path)

    for i, scene in enumerate(scenes, 1):
        if scene.visual_type not in ("image", "graphic"):
            continue
        log.info(f"[{i}/{len(scenes)}] Scene {scene.id}: {scene.english_query[:60]}")
        scene.candidates = asset_finder.find_assets(scene)
        # DON'T vision-judge yet — the human will pick
        # Pre-select the first candidate so there's something to show
        if scene.candidates and not scene.chosen_asset:
            scene.chosen_asset = scene.candidates[0]

    # ── Human preview BEFORE vision ─────────────────
    if ENABLE_PREVIEW:
        log.step(6, 8, "Human review")
        from pipeline.preview_server import PreviewServer
        server = PreviewServer(scenes, context=context,
                            original_video=video_path)
        server.start_and_wait()

        # Vision model as fallback for scenes the user didn't resolve
        for i, scene in enumerate(scenes, 1):
            if scene.visual_type not in ("image", "graphic"):
                continue
            # If the user picked a candidate or added a custom URL,
            # chosen_asset is already set — skip vision.
            if scene.chosen_asset and Path(scene.chosen_asset).exists():
                continue
            log.info(f"Scene {scene.id}: vision fallback…")
            scene.chosen_asset = vision_judge.judge(scene)
            unload(MODEL_VISION)
    else:
        # No preview — vision judges everything as before
        for scene in scenes:
            if scene.visual_type in ("image", "graphic"):
                scene.chosen_asset = vision_judge.judge(scene)
                unload(MODEL_VISION)

    log.step(7, 8, "Building clips")
    clip_paths = clip_builder.build_all(video_path, scenes)

    log.step(8, 8, "Rendering final video")
    output_path = str(FINAL_DIR / "final_video.mp4")
    renderer.render(clip_paths, video_path, output_path,
                    moments, bg_music, nasheed)

    log.ok(f"Pipeline finished in {(time.time()-t0)/60:.1f} min")
    return output_path