import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {assets, benchmark, demoCase} from "./data";

export const WIDTH = 1920;
export const HEIGHT = 1080;
export const FPS = 30;
export const DURATION_IN_FRAMES = 1980;

const colors = {
  bg: "#070b12",
  panel: "#0f1724",
  panel2: "#111b2b",
  border: "#2b3c56",
  text: "#f4f7fb",
  muted: "#9fb0c8",
  dim: "#65758f",
  cyan: "#39d7cf",
  green: "#6ae77d",
  blue: "#5a9fff",
  amber: "#ffcb5a",
  orange: "#ff7a1a",
  red: "#ff6767",
};

const font = {
  display:
    '"Avenir Next", "SF Pro Display", "Helvetica Neue", Helvetica, sans-serif',
  mono:
    '"SF Mono", "JetBrains Mono", "Menlo", "Monaco", "Consolas", monospace',
};

const scene = {
  title: {from: 0, duration: 165},
  race: {from: 135, duration: 360},
  loops: {from: 465, duration: 390},
  visual: {from: 825, duration: 300},
  demo: {from: 1095, duration: 375},
  benchmark: {from: 1410, duration: 390},
  close: {from: 1740, duration: 240},
};

const clamp = (value: number, min = 0, max = 1) =>
  Math.min(max, Math.max(min, value));

const ease = (value: number) => Easing.out(Easing.cubic)(clamp(value));

const progress = (frame: number, start: number, duration: number) =>
  ease((frame - start) / duration);

const fadeOpacity = (
  frame: number,
  duration: number,
  inFrames = 18,
  outFrames = 18,
) => {
  const fadeIn = interpolate(frame, [0, inFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(frame, [duration - outFrames, duration], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return Math.min(fadeIn, fadeOut);
};

const count = (frame: number, to: number, start: number, duration: number) =>
  Math.round(to * progress(frame, start, duration));

const decimalCount = (
  frame: number,
  to: number,
  start: number,
  duration: number,
  digits = 1,
) => (to * progress(frame, start, duration)).toFixed(digits);

const bgLine = "rgba(82, 124, 170, 0.12)";

const Background = () => {
  const frame = useCurrentFrame();
  const drift = (frame * 0.28) % 110;
  return (
    <AbsoluteFill style={{backgroundColor: colors.bg, overflow: "hidden"}}>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 18% 15%, rgba(57,215,207,0.10), transparent 31%), radial-gradient(circle at 80% 10%, rgba(90,159,255,0.08), transparent 26%), linear-gradient(135deg, #070b12 0%, #0a111d 55%, #070b12 100%)",
        }}
      />
      <AbsoluteFill
        style={{
          transform: `translateX(${-drift}px) skewX(-10deg)`,
          backgroundImage: `repeating-linear-gradient(100deg, transparent 0px, transparent 95px, ${bgLine} 96px, transparent 97px)`,
          opacity: 0.72,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.018) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          opacity: 0.45,
        }}
      />
    </AbsoluteFill>
  );
};

const Shell = ({children}: {children: React.ReactNode}) => (
  <AbsoluteFill>
    <Background />
    <AbsoluteFill style={{padding: "70px 88px"}}>{children}</AbsoluteFill>
  </AbsoluteFill>
);

const Eyebrow = ({children}: {children: React.ReactNode}) => (
  <div
    style={{
      fontFamily: font.mono,
      fontSize: 24,
      letterSpacing: 0.8,
      color: colors.cyan,
      textTransform: "uppercase",
    }}
  >
    {children}
  </div>
);

const Headline = ({
  children,
  size = 82,
  maxWidth = 1250,
}: {
  children: React.ReactNode;
  size?: number;
  maxWidth?: number;
}) => (
  <h1
    style={{
      margin: 0,
      maxWidth,
      color: colors.text,
      fontFamily: font.display,
      fontSize: size,
      fontWeight: 520,
      letterSpacing: -2.5,
      lineHeight: 0.98,
    }}
  >
    {children}
  </h1>
);

const Subhead = ({
  children,
  maxWidth = 1120,
}: {
  children: React.ReactNode;
  maxWidth?: number;
}) => (
  <p
    style={{
      margin: "22px 0 0",
      maxWidth,
      color: colors.muted,
      fontFamily: font.display,
      fontSize: 36,
      fontWeight: 400,
      lineHeight: 1.22,
    }}
  >
    {children}
  </p>
);

const Panel = ({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) => (
  <div
    style={{
      background:
        "linear-gradient(180deg, rgba(17,27,43,0.96), rgba(11,18,31,0.96))",
      border: `1px solid ${colors.border}`,
      borderRadius: 28,
      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.05)",
      ...style,
    }}
  >
    {children}
  </div>
);

const Pill = ({
  children,
  color = colors.cyan,
  dim = false,
}: {
  children: React.ReactNode;
  color?: string;
  dim?: boolean;
}) => (
  <div
    style={{
      border: `1px solid ${dim ? colors.border : color}`,
      color: dim ? colors.muted : color,
      borderRadius: 999,
      padding: "10px 16px",
      fontFamily: font.mono,
      fontSize: 23,
      lineHeight: 1,
      background: dim ? "rgba(255,255,255,0.025)" : "rgba(57,215,207,0.06)",
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </div>
);

const AssetImage = ({
  src,
  style,
}: {
  src: string;
  style?: React.CSSProperties;
}) => (
  <Img
    src={staticFile(src)}
    style={{
      width: "100%",
      height: "100%",
      objectFit: "cover",
      display: "block",
      ...style,
    }}
  />
);

const TitleScene = () => {
  const frame = useCurrentFrame();
  const opacity = fadeOpacity(frame, scene.title.duration, 14, 24);
  const typed = "BrowserDelta";
  const typedLength = count(frame, typed.length, 6, 42);
  const cursorOn = Math.floor(frame / 12) % 2 === 0;
  const cardIn = progress(frame, 46, 36);

  return (
    <Shell>
      <AbsoluteFill
        style={{
          opacity,
          transform: `translateY(${(1 - cardIn) * 18}px)`,
          padding: "70px 88px",
        }}
      >
        <div style={{position: "absolute", top: 84, right: 94}}>
          <Pill>live MiniWoB eval</Pill>
        </div>
        <div style={{marginTop: 48}}>
          <Eyebrow>semantic compaction for browser agents</Eyebrow>
          <Headline size={118} maxWidth={1320}>
            {typed.slice(0, typedLength)}
            <span style={{color: colors.cyan}}>
              {typedLength < typed.length && cursorOn ? "_" : ""}
            </span>
          </Headline>
          <Subhead>
            Same browser task. Same agent loop. Far less state sent back to the
            model.
          </Subhead>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 36,
            marginTop: 88,
          }}
        >
          <IntroCard
            accent={colors.blue}
            title="Standard browser agent"
            body="Every step can resend a screenshot or the whole page state. The model reasons over mostly repeated information."
            delay={64}
          />
          <IntroCard
            accent={colors.cyan}
            title="BrowserDelta agent"
            body="The browser stream is compressed into what changed, what matters, and when visual evidence is worth sending."
            delay={78}
          />
        </div>
        <div
          style={{
            position: "absolute",
            left: 92,
            bottom: 88,
            fontFamily: font.display,
            fontSize: 46,
            color: colors.amber,
          }}
        >
          {demoCase.task}
          <div
            style={{
              marginTop: 8,
              fontFamily: font.mono,
              fontSize: 22,
              color: colors.muted,
            }}
          >
            demo target
          </div>
        </div>
      </AbsoluteFill>
    </Shell>
  );
};

const IntroCard = ({
  accent,
  title,
  body,
  delay,
}: {
  accent: string;
  title: string;
  body: string;
  delay: number;
}) => {
  const frame = useCurrentFrame();
  const enter = progress(frame, delay, 30);
  return (
    <Panel
      style={{
        height: 310,
        padding: "36px 36px 36px 44px",
        borderLeft: `8px solid ${accent}`,
        opacity: enter,
        transform: `translateY(${(1 - enter) * 28}px)`,
      }}
    >
      <div
        style={{
          color: colors.text,
          fontFamily: font.display,
          fontSize: 36,
          fontWeight: 520,
        }}
      >
        {title}
      </div>
      <div
        style={{
          marginTop: 18,
          maxWidth: 620,
          color: colors.muted,
          fontFamily: font.display,
          fontSize: 31,
          lineHeight: 1.18,
        }}
      >
        {body}
      </div>
    </Panel>
  );
};

const RaceScene = () => {
  const frame = useCurrentFrame();
  const opacity = fadeOpacity(frame, scene.race.duration, 18, 24);
  const compactTokens = decimalCount(
    frame,
    benchmark.compact.avgTokens,
    74,
    96,
    1,
  );
  const fullTokens = decimalCount(
    frame,
    benchmark.fullState.avgTokens,
    74,
    96,
    1,
  );

  return (
    <Shell>
      <AbsoluteFill style={{opacity, padding: "70px 88px"}}>
        <Eyebrow>same browser agent, different observation stream</Eyebrow>
        <Headline size={76} maxWidth={1360}>
          The expensive part is repeated context.
        </Headline>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 38,
            marginTop: 54,
          }}
        >
          <RacePanel
            mode="full_state"
            accent={colors.blue}
            title="Full page state"
            subtitle="Every decision gets the heavy observation again."
            tokenValue={fullTokens}
            large
          />
          <RacePanel
            mode="compact"
            accent={colors.cyan}
            title="Compact observation"
            subtitle="Only the changed browser facts move forward."
            tokenValue={compactTokens}
          />
        </div>
        <div
          style={{
            position: "absolute",
            bottom: 78,
            left: 92,
            display: "flex",
            gap: 14,
            alignItems: "center",
          }}
        >
          <Pill color={colors.green}>
            {decimalCount(frame, benchmark.tokenReductionPct, 128, 58, 1)}% fewer
            decision tokens
          </Pill>
          <Pill dim>full 125-task MiniWoB run</Pill>
        </div>
      </AbsoluteFill>
    </Shell>
  );
};

const RacePanel = ({
  mode,
  accent,
  title,
  subtitle,
  tokenValue,
  large = false,
}: {
  mode: string;
  accent: string;
  title: string;
  subtitle: string;
  tokenValue: string;
  large?: boolean;
}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, 30, 50);
  const streamRows = Array.from({length: large ? 9 : 7}, (_, index) => index);

  return (
    <Panel
      style={{
        height: 655,
        padding: 34,
        borderColor: accent,
        opacity: p,
        transform: `translateY(${(1 - p) * 20}px)`,
      }}
    >
      <div style={{display: "flex", justifyContent: "space-between", gap: 16}}>
        <div>
          <div
            style={{
              fontFamily: font.mono,
              color: accent,
              fontSize: 23,
              marginBottom: 14,
            }}
          >
            {mode}
          </div>
          <div
            style={{
              color: colors.text,
              fontFamily: font.display,
              fontSize: 43,
              fontWeight: 540,
            }}
          >
            {title}
          </div>
          <div
            style={{
              marginTop: 8,
              color: colors.muted,
              fontFamily: font.display,
              fontSize: 25,
            }}
          >
            {subtitle}
          </div>
        </div>
        <div style={{textAlign: "right"}}>
          <div
            style={{
              color: colors.text,
              fontFamily: font.mono,
              fontSize: 48,
              lineHeight: 1,
            }}
          >
            {tokenValue}
          </div>
          <div
            style={{
              marginTop: 8,
              color: colors.muted,
              fontFamily: font.mono,
              fontSize: 20,
            }}
          >
            avg tokens/task
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: 42,
          display: "grid",
          gridTemplateColumns: large ? "1fr" : "0.78fr",
          gap: 12,
        }}
      >
        {streamRows.map((row) => {
          const rowP = progress(frame, 48 + row * 8, 24);
          return (
            <div
              key={row}
              style={{
                opacity: rowP,
                transform: `translateX(${(1 - rowP) * (large ? -28 : 28)}px)`,
                border: `1px solid ${large ? colors.border : "rgba(57,215,207,0.55)"}`,
                background: large
                  ? "rgba(90,159,255,0.055)"
                  : "rgba(57,215,207,0.075)",
                height: large ? 42 : 36,
                borderRadius: 12,
                width: `${large ? 100 : 46 + row * 3}%`,
                display: "flex",
                alignItems: "center",
                padding: "0 15px",
                fontFamily: font.mono,
                color: large ? colors.muted : colors.cyan,
                fontSize: large ? 17 : 18,
              }}
            >
              {large
                ? `screenshot + DOM snapshot step ${row + 1}`
                : row === 3
                  ? "target_hint visible; likely_click_ref=28"
                  : `delta step ${row + 1}: focused/tab/text changed`}
            </div>
          );
        })}
      </div>
    </Panel>
  );
};

const LoopScene = () => {
  const frame = useCurrentFrame();
  const opacity = fadeOpacity(frame, scene.loops.duration, 16, 24);
  const split = progress(frame, 80, 60);
  const loopScale = 0.94 + split * 0.04;

  return (
    <Shell>
      <AbsoluteFill style={{opacity, padding: "70px 88px"}}>
        <Eyebrow>the browser loop changes shape</Eyebrow>
        <Headline size={72} maxWidth={1500}>
          BrowserDelta replaces repeated full state with a browser diff.
        </Headline>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "0.95fr 1.05fr",
            gap: 34,
            marginTop: 48,
          }}
        >
          <ImageCard
            title="Before"
            caption="full state repeated"
            src={assets.standardLoop}
            accent={colors.blue}
            opacity={1 - split * 0.28}
            scale={0.96}
          />
          <ImageCard
            title="After"
            caption="diff first, visual only when needed"
            src={assets.browserDeltaLoop}
            accent={colors.cyan}
            opacity={0.58 + split * 0.42}
            scale={loopScale}
          />
        </div>
      </AbsoluteFill>
    </Shell>
  );
};

const ImageCard = ({
  title,
  caption,
  src,
  accent,
  opacity,
  scale,
}: {
  title: string;
  caption: string;
  src: string;
  accent: string;
  opacity: number;
  scale: number;
}) => (
  <Panel
    style={{
      height: 660,
      overflow: "hidden",
      borderColor: accent,
      opacity,
      transform: `scale(${scale})`,
    }}
  >
    <div
      style={{
        height: 88,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 28px",
        borderBottom: `1px solid ${colors.border}`,
      }}
    >
      <div style={{fontFamily: font.display, fontSize: 32, color: colors.text}}>
        {title}
      </div>
      <div
        style={{
          fontFamily: font.mono,
          color: accent,
          fontSize: 19,
          lineHeight: 1.15,
          maxWidth: 470,
          textAlign: "right",
        }}
      >
        {caption}
      </div>
    </div>
    <div style={{height: 572, padding: 18}}>
      <AssetImage src={src} style={{objectFit: "contain"}} />
    </div>
  </Panel>
);

const VisualDeltaScene = () => {
  const frame = useCurrentFrame();
  const opacity = fadeOpacity(frame, scene.visual.duration, 16, 24);
  const imageIn = progress(frame, 28, 38);
  const chips = [
    ["DOM/a11y diff first", colors.cyan],
    ["visual regions only when needed", colors.amber],
    ["crop fallback instead of full screenshot", colors.green],
  ] as const;

  return (
    <Shell>
      <AbsoluteFill style={{opacity, padding: "70px 88px"}}>
        <Eyebrow>visual changes do not break the contract</Eyebrow>
        <Headline size={76} maxWidth={1320}>
          VisualDelta escalates only when pixels matter.
        </Headline>
        <div style={{display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 42, marginTop: 48}}>
          <Panel
            style={{
              height: 635,
              overflow: "hidden",
              opacity: imageIn,
              transform: `translateX(${(1 - imageIn) * -28}px)`,
              padding: 18,
            }}
          >
            <AssetImage src={assets.visualDeltaPolicy} style={{objectFit: "contain"}} />
          </Panel>
          <div style={{display: "flex", flexDirection: "column", gap: 24, paddingTop: 34}}>
            {chips.map(([label, color], index) => {
              const itemIn = progress(frame, 70 + index * 28, 26);
              return (
                <Panel
                  key={label}
                  style={{
                    padding: 30,
                    borderColor: color,
                    opacity: itemIn,
                    transform: `translateX(${(1 - itemIn) * 36}px)`,
                  }}
                >
                  <div
                    style={{
                      fontFamily: font.mono,
                      color,
                      fontSize: 24,
                      marginBottom: 14,
                    }}
                  >
                    0{index + 1}
                  </div>
                  <div
                    style={{
                      fontFamily: font.display,
                      color: colors.text,
                      fontSize: 40,
                      lineHeight: 1.08,
                    }}
                  >
                    {label}
                  </div>
                </Panel>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>
    </Shell>
  );
};

const DemoMomentScene = () => {
  const frame = useCurrentFrame();
  const opacity = fadeOpacity(frame, scene.demo.duration, 16, 28);
  const screenshotIn = progress(frame, 28, 42);
  const callout = progress(frame, 110, 34);
  const refPulse = spring({
    frame: Math.max(0, frame - 120),
    fps: FPS,
    config: {damping: 12, mass: 0.7, stiffness: 120},
  });

  return (
    <Shell>
      <AbsoluteFill style={{opacity, padding: "70px 88px"}}>
        <Eyebrow>demo moment</Eyebrow>
        <Headline size={70} maxWidth={1600}>
          The target is found from text diff. No screenshot is sent.
        </Headline>
        <div
          style={{
            marginTop: 40,
            display: "grid",
            gridTemplateColumns: "1.25fr 0.75fr",
            gap: 32,
          }}
        >
          <Panel
            style={{
              height: 700,
              overflow: "hidden",
              opacity: screenshotIn,
              transform: `scale(${0.96 + screenshotIn * 0.04})`,
              padding: 16,
            }}
          >
            <AssetImage src={assets.targetFound} style={{objectFit: "contain"}} />
          </Panel>
          <div style={{display: "flex", flexDirection: "column", gap: 24}}>
            <Panel
              style={{
                padding: 34,
                borderColor: colors.cyan,
                opacity: callout,
                transform: `translateY(${(1 - callout) * 24}px)`,
              }}
            >
              <div
                style={{
                  fontFamily: font.mono,
                  fontSize: 23,
                  color: colors.cyan,
                  marginBottom: 22,
                }}
              >
                compact observation
              </div>
              <CodeLine color={colors.text}>target_hint="faucibus" visible</CodeLine>
              <CodeLine color={colors.green}>
                likely_click_ref={demoCase.targetRef}
              </CodeLine>
              <CodeLine color={colors.muted}>No image sent. Text diff only.</CodeLine>
            </Panel>
            <Panel
              style={{
                padding: 34,
                borderColor: colors.green,
                opacity: callout,
              }}
            >
              <div style={{fontFamily: font.display, color: colors.text, fontSize: 34}}>
                Compact run
              </div>
              <div
                style={{
                  marginTop: 14,
                  color: colors.green,
                  fontFamily: font.mono,
                  fontSize: 62,
                  transform: `scale(${1 + refPulse * 0.035})`,
                  transformOrigin: "left center",
                }}
              >
                solved {demoCase.compactResult}
              </div>
              <TokenRow label="compact" value={demoCase.compactTokens} color={colors.cyan} />
              <TokenRow label="full_state" value={demoCase.fullStateTokens} color={colors.blue} />
            </Panel>
          </div>
        </div>
      </AbsoluteFill>
    </Shell>
  );
};

const CodeLine = ({children, color}: {children: React.ReactNode; color: string}) => (
  <div
    style={{
      fontFamily: font.mono,
      color,
      fontSize: 29,
      lineHeight: 1.42,
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </div>
);

const TokenRow = ({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) => {
  const max = demoCase.fullStateTokens;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "140px 1fr 92px",
        gap: 18,
        alignItems: "center",
        marginTop: 18,
        fontFamily: font.mono,
        color: colors.muted,
        fontSize: 20,
      }}
    >
      <div>{label}</div>
      <div
        style={{
          height: 14,
          borderRadius: 999,
          background: "rgba(255,255,255,0.08)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${(value / max) * 100}%`,
            height: "100%",
            borderRadius: 999,
            background: color,
          }}
        />
      </div>
      <div style={{color}}>{value.toLocaleString("en-US")}</div>
    </div>
  );
};

const BenchmarkScene = () => {
  const frame = useCurrentFrame();
  const opacity = fadeOpacity(frame, scene.benchmark.duration, 16, 26);
  const statIn = progress(frame, 34, 42);
  const reduction = decimalCount(
    frame,
    benchmark.tokenReductionPct,
    80,
    82,
    1,
  );

  return (
    <Shell>
      <AbsoluteFill style={{opacity, padding: "70px 88px"}}>
        <Eyebrow>external benchmark readout</Eyebrow>
        <Headline size={72} maxWidth={1500}>
          Near-parity success, roughly one-sixth the context.
        </Headline>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "0.95fr 1.05fr",
            gap: 36,
            marginTop: 44,
          }}
        >
          <Panel style={{height: 650, padding: 38}}>
            <div style={{fontFamily: font.display, color: colors.text, fontSize: 36}}>
              Task success
            </div>
            <div
              style={{
                marginTop: 10,
                color: colors.muted,
                fontFamily: font.display,
                fontSize: 24,
              }}
            >
              {benchmark.tasks} BrowserGym/MiniWoB tasks, LLM policy
            </div>
            <BarPair
              frame={frame}
              topLabel="BrowserDelta"
              topValue={benchmark.compact.successes}
              topMax={benchmark.tasks}
              topColor={colors.green}
              bottomLabel="full_state"
              bottomValue={benchmark.fullState.successes}
              bottomMax={benchmark.tasks}
              bottomColor={colors.blue}
              delay={76}
              suffix={`/${benchmark.tasks}`}
            />
            <div
              style={{
                marginTop: 64,
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 18,
              }}
            >
              <SmallStat label="same result" value={benchmark.sameResultTasks} color={colors.muted} />
              <SmallStat
                label="compact wins / regressions"
                value={`+${benchmark.compactOnlyWins} / -${benchmark.compactRegressions}`}
                color={colors.cyan}
              />
            </div>
          </Panel>
          <Panel style={{height: 650, padding: 38}}>
            <div style={{fontFamily: font.display, color: colors.text, fontSize: 36}}>
              Average decision tokens
            </div>
            <div
              style={{
                marginTop: 10,
                color: colors.muted,
                fontFamily: font.display,
                fontSize: 24,
              }}
            >
              Context sent to the model per task
            </div>
            <BarPair
              frame={frame}
              topLabel="BrowserDelta"
              topValue={benchmark.compact.avgTokens}
              topMax={benchmark.fullState.avgTokens}
              topColor={colors.cyan}
              bottomLabel="full_state"
              bottomValue={benchmark.fullState.avgTokens}
              bottomMax={benchmark.fullState.avgTokens}
              bottomColor={colors.orange}
              delay={88}
              decimals
            />
            <div
              style={{
                opacity: statIn,
                marginTop: 54,
                fontFamily: font.display,
                color: colors.green,
                fontSize: 82,
                lineHeight: 1,
              }}
            >
              {reduction}% fewer tokens
            </div>
          </Panel>
        </div>
      </AbsoluteFill>
    </Shell>
  );
};

const BarPair = ({
  frame,
  topLabel,
  topValue,
  topMax,
  topColor,
  bottomLabel,
  bottomValue,
  bottomMax,
  bottomColor,
  delay,
  suffix = "",
  decimals = false,
}: {
  frame: number;
  topLabel: string;
  topValue: number;
  topMax: number;
  topColor: string;
  bottomLabel: string;
  bottomValue: number;
  bottomMax: number;
  bottomColor: string;
  delay: number;
  suffix?: string;
  decimals?: boolean;
}) => {
  const topP = progress(frame, delay, 54);
  const bottomP = progress(frame, delay + 16, 54);
  return (
    <div style={{marginTop: 86}}>
      <MetricBar
        label={topLabel}
        value={topValue}
        max={topMax}
        color={topColor}
        progressValue={topP}
        suffix={suffix}
        decimals={decimals}
      />
      <MetricBar
        label={bottomLabel}
        value={bottomValue}
        max={bottomMax}
        color={bottomColor}
        progressValue={bottomP}
        suffix={suffix}
        decimals={decimals}
      />
    </div>
  );
};

const MetricBar = ({
  label,
  value,
  max,
  color,
  progressValue,
  suffix,
  decimals,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
  progressValue: number;
  suffix: string;
  decimals: boolean;
}) => (
  <div style={{marginBottom: 44}}>
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        color: colors.text,
        fontFamily: font.mono,
        fontSize: 28,
        marginBottom: 16,
      }}
    >
      <span>{label}</span>
      <span style={{color}}>
        {decimals ? value.toFixed(1) : Math.round(value)}
        {suffix}
      </span>
    </div>
    <div
      style={{
        height: 42,
        borderRadius: 999,
        background: "rgba(255,255,255,0.08)",
        overflow: "hidden",
        border: `1px solid ${colors.border}`,
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${(value / max) * progressValue * 100}%`,
          borderRadius: 999,
          background: color,
        }}
      />
    </div>
  </div>
);

const SmallStat = ({
  label,
  value,
  color,
}: {
  label: string;
  value: React.ReactNode;
  color: string;
}) => (
  <div
    style={{
      borderTop: `1px solid ${colors.border}`,
      paddingTop: 18,
      fontFamily: font.display,
    }}
  >
    <div style={{color: colors.muted, fontSize: 23}}>{label}</div>
    <div style={{color, marginTop: 8, fontSize: 42}}>{value}</div>
  </div>
);

const CloseScene = () => {
  const frame = useCurrentFrame();
  const opacity = fadeOpacity(frame, scene.close.duration, 18, 40);
  const glow = spring({
    frame,
    fps: FPS,
    config: {damping: 16, stiffness: 75, mass: 1},
  });

  return (
    <Shell>
      <AbsoluteFill
        style={{
          opacity,
          padding: "70px 88px",
          justifyContent: "center",
          alignItems: "center",
          textAlign: "center",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 218,
            color: "rgba(57,215,207,0.10)",
            fontFamily: font.mono,
            fontSize: 220,
            lineHeight: 1,
            transform: `scale(${0.96 + glow * 0.04})`,
          }}
        >
          84.0%
        </div>
        <div style={{position: "relative"}}>
          <Eyebrow>BrowserDelta</Eyebrow>
          <Headline size={104} maxWidth={1280}>
            Less context. Same decisions.
          </Headline>
          <Subhead maxWidth={950}>
            A compaction layer for browser agents that sends the browser diff
            instead of resending the page.
          </Subhead>
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: 14,
              marginTop: 42,
            }}
          >
            <Pill color={colors.green}>48/125 compact</Pill>
            <Pill color={colors.blue}>50/125 full_state</Pill>
            <Pill color={colors.cyan}>84.0% token reduction</Pill>
          </div>
        </div>
      </AbsoluteFill>
    </Shell>
  );
};

export const BrowserDeltaDemo = () => {
  return (
    <AbsoluteFill style={{backgroundColor: colors.bg}}>
      <Sequence from={scene.title.from} durationInFrames={scene.title.duration}>
        <TitleScene />
      </Sequence>
      <Sequence from={scene.race.from} durationInFrames={scene.race.duration}>
        <RaceScene />
      </Sequence>
      <Sequence from={scene.loops.from} durationInFrames={scene.loops.duration}>
        <LoopScene />
      </Sequence>
      <Sequence from={scene.visual.from} durationInFrames={scene.visual.duration}>
        <VisualDeltaScene />
      </Sequence>
      <Sequence from={scene.demo.from} durationInFrames={scene.demo.duration}>
        <DemoMomentScene />
      </Sequence>
      <Sequence
        from={scene.benchmark.from}
        durationInFrames={scene.benchmark.duration}
      >
        <BenchmarkScene />
      </Sequence>
      <Sequence from={scene.close.from} durationInFrames={scene.close.duration}>
        <CloseScene />
      </Sequence>
    </AbsoluteFill>
  );
};
