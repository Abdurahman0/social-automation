/* The owner's reel: real B-roll (video or photo) per script part, infographic numbers, the title at the top and the
   subtitles at eye level. Every text box comes from `layout`, computed in Python (socialauto/reel/layout.py) and checked
   there against Instagram's UI safe zones (nothing in the bottom ~20 % or at the right edge). Audio is mixed and muxed
   afterwards by ffmpeg (voice ducking + -14 LUFS), so this composition is silent. */
import React from "react";
import {
  AbsoluteFill, Img, Loop, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";

type Box = { x: number; y: number; w: number; h: number };
type Word = { w: string; s: number; e: number };
export type Scene = {
  part: string; start: number; end: number;
  media: { type: "video" | "image"; src: string; seconds?: number };
  info?: { value: string; label: string } | null;
};
export type ReelProps = {
  width: number; height: number; fps: number; duration: number;
  title: string; scenes: Scene[]; lines: { start: number; end: number; words: Word[] }[];
  layout: { title: Box; subtitle: Box; info: Box };
  style: { accent: string; titleSize: number; subtitleSize: number; infoSize: number; font: string };
};

export const defaultProps: ReelProps = {
  width: 1080, height: 1920, fps: 30, duration: 10, title: "Preview", scenes: [], lines: [],
  layout: { title: { x: 64, y: 150, w: 856, h: 220 }, subtitle: { x: 64, y: 1060, w: 856, h: 260 },
            info: { x: 64, y: 560, w: 856, h: 360 } },
  style: { accent: "#38bdf8", titleSize: 64, subtitleSize: 64, infoSize: 150, font: "Montserrat" },
};

const FontFace: React.FC<{ font: string }> = ({ font }) => (
  <style>{`@font-face { font-family: '${font}'; src: url('${staticFile("_fonts/Montserrat-ExtraBold.ttf")}'); font-weight: 800; }
@font-face { font-family: '${font}'; src: url('${staticFile("_fonts/Montserrat-Bold.ttf")}'); font-weight: 700; }`}</style>
);

const Media: React.FC<{ scene: Scene; frames: number }> = ({ scene, frames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const zoom = interpolate(frame, [0, frames], [1.06, 1.16], { extrapolateRight: "clamp" });
  const drift = interpolate(frame, [0, frames], [0, -30], { extrapolateRight: "clamp" });
  const style: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover",
    transform: `scale(${zoom}) translateY(${drift}px)` };
  if (scene.media.type === "video") {
    const clipFrames = Math.max(1, Math.round((scene.media.seconds || frames / fps) * fps));
    return (
      <Loop durationInFrames={Math.min(clipFrames, Math.max(1, frames))}>
        <OffthreadVideo src={staticFile(scene.media.src)} muted style={style} />
      </Loop>
    );
  }
  return <Img src={staticFile(scene.media.src)} style={style} />;
};

const Shade: React.FC = () => (
  <AbsoluteFill style={{ background:
    "linear-gradient(180deg, rgba(4,12,20,.78) 0%, rgba(4,12,20,.15) 28%, rgba(4,12,20,.10) 50%, rgba(4,12,20,.55) 72%, rgba(4,12,20,.80) 100%)" }} />
);

const Title: React.FC<{ text: string; box: Box; size: number; accent: string; font: string }> = ({ text, box, size, accent, font }) => (
  <div style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h, display: "flex",
    flexDirection: "column", justifyContent: "flex-start", fontFamily: font }}>
    <div style={{ width: 90, height: 10, borderRadius: 5, background: accent, marginBottom: 22 }} />
    <div style={{ color: "#fff", fontWeight: 800, fontSize: size, lineHeight: 1.1, textShadow: "0 4px 18px rgba(0,0,0,.6)",
      overflowWrap: "break-word" }}>{text}</div>
  </div>
);

const Info: React.FC<{ info: NonNullable<Scene["info"]>; box: Box; size: number; accent: string; font: string }> = ({ info, box, size, accent, font }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 14 } });
  return (
    <div style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h, display: "flex",
      flexDirection: "column", justifyContent: "center", alignItems: "flex-start", fontFamily: font,
      transform: `scale(${0.85 + 0.15 * pop})`, opacity: pop, transformOrigin: "left center" }}>
      <div style={{ background: "rgba(4,12,20,.62)", borderLeft: `14px solid ${accent}`, borderRadius: 24, padding: "28px 36px",
        maxWidth: box.w }}>
        <div style={{ color: accent, fontWeight: 800, fontSize: size, lineHeight: 1 }}>{info.value}</div>
        <div style={{ color: "#fff", fontWeight: 700, fontSize: Math.round(size * 0.3), marginTop: 14, lineHeight: 1.2 }}>{info.label}</div>
      </div>
    </div>
  );
};

const Subtitles: React.FC<{ lines: ReelProps["lines"]; box: Box; size: number; accent: string; font: string }> = ({ lines, box, size, accent, font }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const line = lines.find((l) => t >= l.start && t < l.end);
  if (!line) return null;
  return (
    <div style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h, display: "flex",
      alignItems: "center", justifyContent: "center", textAlign: "center", fontFamily: font }}>
      <div style={{ fontWeight: 800, fontSize: size, lineHeight: 1.18, color: "#fff", textTransform: "uppercase",
        textShadow: "0 0 3px #000, 0 4px 16px rgba(0,0,0,.85)", overflowWrap: "break-word" }}>
        {line.words.map((w, i) => (
          <span key={i} style={{ color: t >= w.s && t < (line.words[i + 1]?.s ?? line.end) ? accent : "#fff" }}>{w.w}{" "}</span>
        ))}
      </div>
    </div>
  );
};

export const Reel: React.FC<ReelProps> = (p) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "#04121c" }}>
      <FontFace font={p.style.font} />
      {p.scenes.map((sc, i) => {
        const from = Math.round(sc.start * fps);
        const frames = Math.max(1, Math.round(sc.end * fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={frames}>
            <AbsoluteFill><Media scene={sc} frames={frames} /></AbsoluteFill>
            <Shade />
            {sc.info ? <Info info={sc.info} box={p.layout.info} size={p.style.infoSize} accent={p.style.accent} font={p.style.font} /> : null}
          </Sequence>
        );
      })}
      <Title text={p.title} box={p.layout.title} size={p.style.titleSize} accent={p.style.accent} font={p.style.font} />
      <Subtitles lines={p.lines} box={p.layout.subtitle} size={p.style.subtitleSize} accent={p.style.accent} font={p.style.font} />
    </AbsoluteFill>
  );
};
