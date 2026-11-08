import React from "react";
import { Composition } from "remotion";
import { Reel, ReelProps, defaultProps } from "./Reel";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Reel"
    component={Reel as unknown as React.FC<Record<string, unknown>>}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={300}
    defaultProps={defaultProps as unknown as Record<string, unknown>}
    calculateMetadata={({ props }) => {
      const p = props as unknown as ReelProps;
      return { durationInFrames: Math.max(1, Math.round(p.duration * p.fps)), fps: p.fps, width: p.width, height: p.height };
    }}
  />
);
