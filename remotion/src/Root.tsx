import React from "react";
import { Composition } from "remotion";
import { TEMPLATES, TEXT_TEMPLATES, type TemplateId } from "./registry";

const FPS = 30;

const toCompositionId = (id: TemplateId): string => {
  return id.replace(/_/g, "-");
};

export const RemotionRoot: React.FC = () => (
  <>
    {(Object.keys(TEMPLATES) as TemplateId[]).map((id) => {
      const def = TEMPLATES[id];
      const isText = TEXT_TEMPLATES.includes(id);

      // Remotion IDs cannot contain underscores.
      // Keep the internal template ID unchanged.
      const compositionId = toCompositionId(id);

      return (
        <Composition
          key={compositionId}
          id={compositionId}
          component={def.component as any}
          width={1920}
          height={1080}
          fps={FPS}
          defaultProps={def.defaultProps as any}
          calculateMetadata={({ props }) => {
            const p = props as any;

            // Priority 1: explicit frame count (pipeline sends this)
            if (
              typeof p?.durationInFrames === "number" &&
              p.durationInFrames > 0
            ) {
              return {
                durationInFrames: p.durationInFrames,
              };
            }

            // Priority 2: text templates auto-size from totalReadingSeconds
            if (
              isText &&
              typeof p?.totalReadingSeconds === "number" &&
              p.totalReadingSeconds > 0
            ) {
              return {
                durationInFrames: Math.round(
                  p.totalReadingSeconds * FPS
                ),
              };
            }

            // Priority 3: fall back to the default
            return {
              durationInFrames: def.defaultDurationInFrames,
            };
          }}
        />
      );
    })}
  </>
);