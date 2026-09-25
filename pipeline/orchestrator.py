"""Coordinates the full pipeline. Single entry point."""
import time
from pathlib import Path

from config import FINAL_DIR, MODEL_VISION
from pipeline import (
    transcriber, context_extractor, scene_planner, query_generator,
    asset_finder, vision_judge, audio_analyzer, clip_builder, renderer,
)
from utils.logger import log
from utils.ollama_client import unload


TOTAL_STEPS = 7


def run(video_path: str, bg_music: str | None = None,
        nasheed: str | None = None) -> str:
    t0 = time.time()
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    log.step(1, TOTAL_STEPS, "Transcribing (mlx-whisper)")
    log.info(f"Input: {video_path}")
    segments = transcriber.transcribe(video_path)
    transcript_text = transcriber.to_timestamped_text(segments)

    log.step(2, TOTAL_STEPS, "Extracting global context")
    context = context_extractor.extract_context(transcript_text)

    log.step(3, TOTAL_STEPS, "Planning scenes")
    scenes, moments = scene_planner.plan(transcript_text, context=context)
    log.info(f"Scenes: {[s.id for s in scenes]}")

    log.step(4, TOTAL_STEPS, "Refining search queries")
    scenes = query_generator.generate_queries(scenes, context)

    log.step(5, TOTAL_STEPS, "Analyzing audio + searching assets")
    audio_analyzer.analyze(video_path)

    for i, scene in enumerate(scenes, 1):
        if scene.visual_type not in ("image", "graphic"):
            log.info(f"Scene {scene.id}: skip (visual_type={scene.visual_type})")
            continue
        log.info(f"[{i}/{len(scenes)}] Scene {scene.id}: {scene.english_query[:60]}")
        scene.candidates = asset_finder.find_assets(scene)
        log.info(f"  → {len(scene.candidates)} candidates")
        scene.chosen_asset = vision_judge.judge(scene)
        chosen_name = Path(scene.chosen_asset).name if scene.chosen_asset else "none"
        log.info(f"  → chosen: {chosen_name}")
        unload(MODEL_VISION)

    log.step(6, TOTAL_STEPS, "Building clips")
    clip_paths = clip_builder.build_all(video_path, scenes)

    log.step(7, TOTAL_STEPS, "Rendering final video")
    output_path = str(FINAL_DIR / "final_video.mp4")
    renderer.render(
        clip_paths=clip_paths,
        narration_video=video_path,
        output_path=output_path,
        important_moments=moments,
        bg_music=bg_music,
        nasheed=nasheed,
    )

    elapsed = (time.time() - t0) / 60
    log.ok(f"Pipeline finished in {elapsed:.1f} min")
    return output_path