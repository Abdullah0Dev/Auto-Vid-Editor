"""Orchestration layer for planning + rendering Remotion graphics."""

from __future__ import annotations

from config import (
    ENABLE_GRAPHICS,
    GRAPHIC_MAX_DURATION,
)
from models.types import Scene
from pipeline import graphic_planner, graphic_renderer
from utils.logger import log


def plan_graphic_scenes(
    scenes: list[Scene],
    context: dict | None = None,
) -> None:
    """
    Plan every scene marked visual_type='graphic'.

    Failed graphic plans are converted back to image scenes so
    the normal asset_finder can handle them.
    """

    if not ENABLE_GRAPHICS:
        return

    for scene in scenes:
        if scene.visual_type != "graphic":
            continue

        duration = scene.end - scene.start

        if duration <= 0:
            scene.visual_type = "image"
            continue

        if duration > GRAPHIC_MAX_DURATION:
            log.warn(
                f"Scene {scene.id}: "
                f"graphic too long ({duration:.2f}s), "
                f"falling back to image"
            )

            scene.visual_type = "image"
            continue

        log.info(
            f"[graphics] "
            f"Scene {scene.id}: planning "
            f"({duration:.2f}s)"
        )

        plan = graphic_planner.plan_graphic(
            scene,
            context,
        )

        if not plan:
            log.warn(
                f"Scene {scene.id}: "
                f"no graphic plan → image fallback"
            )

            scene.visual_type = "image"
            continue

        scene.graphic_template = plan["template"]
        scene.graphic_props = plan["props"]

        log.ok(
            f"Scene {scene.id}: "
            f"planned {plan['template']}"
        )


def render_graphic_scenes(
    scenes: list[Scene],
) -> None:
    """
    Render all successfully planned graphic scenes.

    Duration ALWAYS equals scene.end - scene.start.
    """

    if not ENABLE_GRAPHICS:
        return

    for scene in scenes:
        if (
            scene.visual_type != "graphic"
            or not scene.graphic_template
            or not scene.graphic_props
        ):
            continue

        duration = scene.end - scene.start

        if duration <= 0:
            scene.visual_type = "image"
            continue

        if duration > GRAPHIC_MAX_DURATION:
            log.warn(
                f"Scene {scene.id}: "
                f"graphic duration exceeds safety cap"
            )

            scene.visual_type = "image"
            continue

        try:
            path = graphic_renderer.render_graphic(
                template=scene.graphic_template,
                props=scene.graphic_props,
                duration_seconds=duration,
            )

        except Exception as exc:
            log.warn(
                f"Scene {scene.id}: "
                f"graphic render failed: {exc}"
            )

            # Let normal image fallback handle it.
            scene.visual_type = "image"
            scene.graphic_path = None
            scene.graphic_template = None
            scene.graphic_props = None
            continue

        scene.graphic_path = str(path)
        scene.chosen_asset = str(path)

        log.ok(
            f"Scene {scene.id}: "
            f"graphic ready → {path.name}"
        )