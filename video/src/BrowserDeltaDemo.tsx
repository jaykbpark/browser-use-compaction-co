import React from "react";
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  Sequence,
  Video,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {assets, benchmark, demoCase, internalDemo, transcript} from "./data";

export const WIDTH = 1920;
export const HEIGHT = 1080;
export const FPS = 30;
export const DURATION_IN_FRAMES = 6258;

const frame = (seconds: number) => Math.round(seconds * FPS);

const scenes = {
  intro: {from: frame(0), duration: frame(24.2)},
  problem: {from: frame(24.2), duration: frame(23.7)},
  insight: {from: frame(47.9), duration: frame(18.1)},
  dom: {from: frame(66), duration: frame(20)},
  visual: {from: frame(86), duration: frame(34.2)},
  router: {from: frame(120.2), duration: frame(20.9)},
  demo: {from: frame(141.1), duration: frame(28.8)},
  benchmark: {from: frame(169.9), duration: frame(20.4)},
  close: {from: frame(190.3), duration: frame(18.3)},
};

const palette = {
  paper: "#f7f8f3",
  paper2: "#ffffff",
  ink: "#121611",
  ink2: "#31372f",
  muted: "#687064",
  line: "#d8ddd2",
  lineDark: "#aeb8a9",
  green: "#0b6b2b",
  green2: "#1a8a45",
  cyan: "#188c85",
  blue: "#3b6fb6",
  amber: "#c88316",
  red: "#b43a31",
  black: "#111411",
};

const font = {
  display:
    '"Avenir Next", "SF Pro Display", "Helvetica Neue", Helvetica, sans-serif',
  mono:
    '"SF Mono", "JetBrains Mono", "Menlo", "Monaco", "Consolas", monospace',
};

const stageLabels = [
  "intro",
  "cost",
  "layer",
  "dom diff",
  "visual diff",
  "router",
  "demo",
  "eval",
  "close",
];

const clamp = (value: number, min = 0, max = 1) =>
  Math.min(max, Math.max(min, value));

const ease = (value: number) => Easing.out(Easing.cubic)(clamp(value));

const progress = (frameValue: number, start: number, duration: number) =>
  ease((frameValue - start) / duration);

const fade = (frameValue: number, duration: number, inFrames = 16, outFrames = 16) => {
  const fadeIn = interpolate(frameValue, [0, inFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(frameValue, [duration - outFrames, duration], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return Math.min(fadeIn, fadeOut);
};

const number = (value: number, digits = 0) =>
  value.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });

const Base = ({
  activeIndex,
  children,
}: {
  activeIndex: number;
  children: React.ReactNode;
}) => {
  const f = useCurrentFrame();
  const drift = (f * 0.16) % 80;
  return (
    <AbsoluteFill
      style={{
        background: palette.paper,
        color: palette.ink,
        fontFamily: font.display,
        overflow: "hidden",
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage:
            "linear-gradient(rgba(11,107,43,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(11,107,43,0.05) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          transform: `translateX(${-drift}px)`,
          opacity: 0.62,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 82% 8%, rgba(24,140,133,0.10), transparent 30%), radial-gradient(circle at 4% 84%, rgba(11,107,43,0.08), transparent 32%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 120,
          right: 120,
          top: 42,
          height: 34,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          color: palette.muted,
          fontFamily: font.mono,
          fontSize: 15,
          letterSpacing: 0,
        }}
      >
        <span>BrowserDelta</span>
        <div style={{display: "flex", gap: 10, alignItems: "center"}}>
          {stageLabels.map((label, index) => (
            <span
              key={label}
              style={{
                padding: "5px 9px",
                borderRadius: 999,
                border: `1px solid ${
                  index === activeIndex ? palette.green : "transparent"
                }`,
                color: index === activeIndex ? palette.green : palette.muted,
                background:
                  index === activeIndex ? "rgba(11,107,43,0.06)" : "transparent",
              }}
            >
              {label}
            </span>
          ))}
        </div>
      </div>
      <div style={{position: "absolute", inset: "92px 120px 78px"}}>
        {children}
      </div>
    </AbsoluteFill>
  );
};

const Kicker = ({children}: {children: React.ReactNode}) => (
  <div
    style={{
      fontFamily: font.mono,
      color: palette.green,
      fontSize: 24,
      letterSpacing: 0,
      textTransform: "uppercase",
      marginBottom: 16,
    }}
  >
    {children}
  </div>
);

const Title = ({
  children,
  size = 84,
  maxWidth = 1240,
}: {
  children: React.ReactNode;
  size?: number;
  maxWidth?: number;
}) => (
  <h1
    style={{
      margin: 0,
      maxWidth,
      fontSize: size,
      lineHeight: 1.0,
      letterSpacing: -2,
      fontWeight: 620,
      color: palette.ink,
    }}
  >
    {children}
  </h1>
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
      background: "rgba(255,255,255,0.84)",
      border: `1px solid ${palette.line}`,
      borderRadius: 26,
      boxShadow: "0 24px 60px rgba(30, 42, 30, 0.08)",
      overflow: "hidden",
      ...style,
    }}
  >
    {children}
  </div>
);

const Capture = ({
  src,
  title,
  style,
}: {
  src: string;
  title?: string;
  style?: React.CSSProperties;
}) => (
  <Panel style={{padding: 14, ...style}}>
    {title ? (
      <div
        style={{
          height: 34,
          display: "flex",
          alignItems: "center",
          color: palette.muted,
          fontFamily: font.mono,
          fontSize: 15,
          padding: "0 6px 10px",
        }}
      >
        {title}
      </div>
    ) : null}
    <Img
      src={staticFile(src)}
      style={{
        display: "block",
        width: "100%",
        height: title ? "calc(100% - 34px)" : "100%",
        objectFit: "contain",
        borderRadius: 14,
      }}
    />
  </Panel>
);

const StatPill = ({
  label,
  value,
  tone = "green",
}: {
  label: string;
  value: string;
  tone?: "green" | "blue" | "amber" | "red" | "ink";
}) => {
  const color =
    tone === "blue"
      ? palette.blue
      : tone === "amber"
        ? palette.amber
        : tone === "red"
          ? palette.red
          : tone === "ink"
            ? palette.ink
            : palette.green;
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        gap: 12,
        padding: "13px 18px",
        border: `1px solid ${color}`,
        borderRadius: 999,
        color,
        background: "rgba(255,255,255,0.70)",
        fontFamily: font.mono,
      }}
    >
      <strong style={{fontSize: 26, fontWeight: 700}}>{value}</strong>
      <span style={{fontSize: 17, color: palette.muted}}>{label}</span>
    </div>
  );
};

export const BrowserDeltaDemo = () => {
  return (
    <AbsoluteFill>
      <Audio src={staticFile(assets.voiceover)} />
      <Sequence from={scenes.intro.from} durationInFrames={scenes.intro.duration}>
        <IntroScene />
      </Sequence>
      <Sequence from={scenes.problem.from} durationInFrames={scenes.problem.duration}>
        <ProblemScene />
      </Sequence>
      <Sequence from={scenes.insight.from} durationInFrames={scenes.insight.duration}>
        <InsightScene />
      </Sequence>
      <Sequence from={scenes.dom.from} durationInFrames={scenes.dom.duration}>
        <DomScene />
      </Sequence>
      <Sequence from={scenes.visual.from} durationInFrames={scenes.visual.duration}>
        <VisualScene />
      </Sequence>
      <Sequence from={scenes.router.from} durationInFrames={scenes.router.duration}>
        <RouterScene />
      </Sequence>
      <Sequence from={scenes.demo.from} durationInFrames={scenes.demo.duration}>
        <DemoScene />
      </Sequence>
      <Sequence
        from={scenes.benchmark.from}
        durationInFrames={scenes.benchmark.duration}
      >
        <BenchmarkScene />
      </Sequence>
      <Sequence from={scenes.close.from} durationInFrames={scenes.close.duration}>
        <CloseScene />
      </Sequence>
    </AbsoluteFill>
  );
};

const IntroScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.intro.duration, 16, 12);
  const bubbleOut = progress(f, frame(16.2), frame(1.2));
  const titleIn = progress(f, frame(1.2), frame(1.0));
  return (
    <Base activeIndex={0}>
      <div style={{opacity, height: "100%", position: "relative"}}>
        <div
          style={{
            position: "absolute",
            top: 115,
            left: 0,
            transform: `translateY(${(1 - titleIn) * 28}px)`,
            opacity: titleIn,
          }}
        >
          <Kicker>changes-only context for browser agents</Kicker>
          <Title size={118} maxWidth={1120}>
            BrowserDelta
          </Title>
          <div
            style={{
              marginTop: 28,
              maxWidth: 930,
              fontSize: 42,
              lineHeight: 1.12,
              color: palette.ink2,
            }}
          >
            A compaction layer that lets browser agents reason over what changed.
          </div>
        </div>
        <div
          style={{
            position: "absolute",
            right: 12,
            bottom: 94,
            width: 444,
            height: 310,
            borderRadius: 42,
            overflow: "hidden",
            border: `1px solid ${palette.lineDark}`,
            background: palette.black,
            boxShadow: "0 28px 80px rgba(18,22,17,0.22)",
            opacity: 1 - bubbleOut,
            transform: `scale(${1 - bubbleOut * 0.28}) translateY(${bubbleOut * 30}px)`,
          }}
        >
          <Video
            src={staticFile(assets.jayIntro)}
            muted
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        </div>
        <div
          style={{
            position: "absolute",
            left: 0,
            bottom: 106,
            display: "flex",
            gap: 14,
            opacity: progress(f, frame(9), frame(1.2)),
          }}
        >
          <StatPill label="watch before/after" value="01" tone="ink" />
          <StatPill label="emit compact observation" value="02" />
        </div>
      </div>
    </Base>
  );
};

const ProblemScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.problem.duration, 12, 12);
  const cycles = Math.min(7, Math.floor(f / 58) + 1);
  const counter = Math.round(interpolate(f, [0, scenes.problem.duration - 70], [0, 19600], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  }));

  return (
    <Base activeIndex={1}>
      <div style={{opacity, height: "100%"}}>
        <Kicker>the problem</Kicker>
        <Title size={74} maxWidth={1260}>
          Browser agents keep paying to reread the whole page.
        </Title>
        <div
          style={{
            marginTop: 50,
            display: "grid",
            gridTemplateColumns: "1.02fr 0.98fr",
            gap: 48,
            height: 632,
          }}
        >
          <Panel style={{padding: 42, position: "relative"}}>
            <div
              style={{
                position: "absolute",
                left: 42,
                right: 42,
                top: 56,
                display: "grid",
                gridTemplateColumns: "170px 72px 206px 72px 170px",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <LoopNode label="browser" tone={palette.green} />
              <InlineArrow />
              <LoopNode label="screenshot" tone={palette.red} active />
              <InlineArrow />
              <LoopNode label="LLM" tone={palette.blue} />
            </div>
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: 206,
                display: "flex",
                justifyContent: "center",
                color: palette.lineDark,
                fontSize: 50,
                fontFamily: font.mono,
              }}
            >
              |
            </div>
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: 116,
                height: 252,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {Array.from({length: cycles}).map((_, index) => (
                <div
                  key={index}
                  style={{
                    position: "absolute",
                    left: `calc(50% - ${168 - index * 18}px)`,
                    top: 22 + index * 13,
                    width: 258,
                    height: 142,
                    borderRadius: 12,
                    border: `1px solid ${palette.red}`,
                    background: "rgba(180,58,49,0.07)",
                    transform: `rotate(${-4 + index * 1.2}deg)`,
                    opacity: 0.28 + index * 0.08,
                  }}
                />
              ))}
              <LoopNode label="action" tone={palette.ink} style={{zIndex: 2}} />
            </div>
            <div
              style={{
                position: "absolute",
                left: 42,
                right: 42,
                bottom: 42,
                fontFamily: font.mono,
                fontSize: 21,
                color: palette.red,
                textAlign: "center",
              }}
            >
              duplicate screenshots stack up
            </div>
          </Panel>
          <Panel
            style={{
              padding: 44,
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{fontFamily: font.mono, color: palette.red, fontSize: 24}}>
                repeated context counter
              </div>
              <div
                style={{
                  marginTop: 26,
                  fontFamily: font.mono,
                  fontSize: 88,
                  lineHeight: 1,
                  fontWeight: 800,
                  color: palette.red,
                }}
              >
                {number(counter)}
              </div>
              <div style={{marginTop: 12, color: palette.muted, fontSize: 30}}>
                screenshot/state tokens resent in the same browser task
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 18,
              }}
            >
              <MiniFact label="state change" value="small" />
              <MiniFact label="payload sent" value="whole page" tone="red" />
            </div>
          </Panel>
        </div>
      </div>
    </Base>
  );
};

const InsightScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.insight.duration, 12, 12);
  const insert = progress(f, frame(4.8), frame(1.3));
  return (
    <Base activeIndex={2}>
      <div style={{opacity, height: "100%"}}>
        <Kicker>the layer</Kicker>
        <Title size={82} maxWidth={1410}>
          Watch the transaction. Send the observation.
        </Title>
        <div
          style={{
            marginTop: 76,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 40,
            height: 590,
          }}
        >
          <LoopCard title="Before" faded>
            <FlowRow items={["browser", "full state", "agent"]} colors={[palette.green, palette.red, palette.blue]} />
            <Payload label="full screenshot + DOM + accessibility tree" tone="red" />
          </LoopCard>
          <LoopCard title="After">
            <div style={{position: "relative", height: 246}}>
              <FlowRow
                items={["browser", "BrowserDelta", "agent"]}
                colors={[palette.green, palette.green, palette.blue]}
                emphasisIndex={1}
                scale={0.96 + insert * 0.04}
              />
            </div>
            <Payload label="summary + route + token estimate + optional crop" />
          </LoopCard>
        </div>
      </div>
    </Base>
  );
};

const DomScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.dom.duration, 12, 12);
  const rows = [
    {time: 4.0, label: "+ button appeared", color: palette.green},
    {time: 8.6, label: "~ visible text changed", color: palette.amber},
    {time: 12.2, label: "* input focused", color: palette.cyan},
  ];
  return (
    <Base activeIndex={3}>
      <div style={{opacity, height: "100%"}}>
        <Kicker>perception angle 01</Kicker>
        <Title size={78} maxWidth={1360}>
          DOM and accessibility diffs catch semantic changes first.
        </Title>
        <div
          style={{
            marginTop: 54,
            display: "grid",
            gridTemplateColumns: "1.1fr 0.9fr",
            gap: 44,
            height: 642,
          }}
        >
          <Capture
            src={assets.viewerFruitDone}
            title="actual BrowserDelta viewer: text-only compact observation"
          />
          <Panel style={{padding: 40}}>
            <div style={{fontFamily: font.mono, fontSize: 22, color: palette.green}}>
              structural_diff.json
            </div>
            <div style={{marginTop: 30, display: "grid", gap: 18}}>
              {rows.map((row) => {
                const on = progress(f, frame(row.time), frame(0.55));
                return (
                  <div
                    key={row.label}
                    style={{
                      opacity: on,
                      transform: `translateX(${(1 - on) * 26}px)`,
                      border: `1px solid ${row.color}`,
                      borderRadius: 16,
                      padding: "20px 22px",
                      background: "rgba(255,255,255,0.76)",
                      fontFamily: font.mono,
                      fontSize: 32,
                      color: row.color,
                    }}
                  >
                    {row.label}
                  </div>
                );
              })}
            </div>
            <div
              style={{
                marginTop: 34,
                borderTop: `1px solid ${palette.line}`,
                paddingTop: 28,
                fontSize: 30,
                lineHeight: 1.24,
                color: palette.ink2,
              }}
            >
              If the browser state explains the next action, no screenshot has to
              move through the model.
            </div>
          </Panel>
        </div>
      </div>
    </Base>
  );
};

const VisualScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.visual.duration, 12, 12);
  const region = progress(f, frame(8), frame(0.9));
  const ocr = progress(f, frame(14.4), frame(0.9));
  const sim = progress(f, frame(22), frame(0.9));
  return (
    <Base activeIndex={4}>
      <div style={{opacity, height: "100%"}}>
        <Kicker>perception angle 02</Kicker>
        <Title size={78} maxWidth={1420}>
          When DOM cannot explain it, compare pixels around the change.
        </Title>
        <div
          style={{
            marginTop: 54,
            display: "grid",
            gridTemplateColumns: "1.02fr 0.98fr",
            gap: 44,
            height: 642,
          }}
        >
          <div style={{position: "relative"}}>
            <Capture
              src={assets.viewerCanvasCrop}
              title="real visual-crop route from the running viewer"
              style={{height: "100%"}}
            />
            <RegionBox left={246} top={190} width={304} height={154} opacity={region} />
            <RegionBox left={610} top={214} width={210} height={132} opacity={region} />
          </div>
          <Panel style={{padding: 38}}>
            <PipelineStep
              index="01"
              title="changed regions"
              body="pixel mask -> connected boxes -> nearby DOM anchors"
              active={region}
              tone={palette.green}
            />
            <PipelineStep
              index="02"
              title="OCR when useful"
              body="read text inside the changed crop, not the full page"
              active={ocr}
              tone={palette.amber}
            />
            <PipelineStep
              index="03"
              title="SSIM + pHash"
              body="score how large or uncertain the visual change is"
              active={sim}
              tone={palette.cyan}
            />
            <div
              style={{
                marginTop: 28,
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 18,
              }}
            >
              <Gauge label="SSIM" value="0.42" active={sim} />
              <Gauge label="pHash delta" value="high" active={sim} />
            </div>
          </Panel>
        </div>
      </div>
    </Base>
  );
};

const RouterScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.router.duration, 12, 12);
  const active = f < frame(7.0) ? 0 : f < frame(13.4) ? 1 : 2;
  const routes = [
    {
      name: "text_only",
      tone: palette.cyan,
      title: "DOM explains it",
      payload: "target_hint visible; button enabled; input focused",
    },
    {
      name: "crop_with_context",
      tone: palette.amber,
      title: "small visual change",
      payload: "summary + one crop + nearby DOM labels",
    },
    {
      name: "full_screenshot",
      tone: palette.red,
      title: "large or uncertain",
      payload: "fallback only when compact evidence is unsafe",
    },
  ];
  return (
    <Base activeIndex={5}>
      <div style={{opacity, height: "100%"}}>
        <Kicker>router</Kicker>
        <Title size={66} maxWidth={1220}>
          Pick the smallest observation that preserves the next action.
        </Title>
        <Panel
          style={{
            position: "relative",
            height: 648,
            marginTop: 42,
            padding: 44,
            background: "rgba(255,255,255,0.66)",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: 62,
              width: 510,
              height: 156,
              marginLeft: -255,
              borderRadius: 26,
              border: `2px solid ${palette.green}`,
              background: "rgba(255,255,255,0.96)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 18px 48px rgba(30,42,30,0.08)",
            }}
          >
            <div style={{fontFamily: font.mono, fontSize: 25, color: palette.green}}>
              BrowserDelta router
            </div>
            <div
              style={{
                marginTop: 14,
                width: "100%",
                textAlign: "center",
                fontSize: 40,
                lineHeight: 1.08,
                fontWeight: 650,
              }}
            >
              how much context?
            </div>
          </div>
          <RouterLine x1={840} y1={218} x2={260} y2={352} active={active === 0} />
          <RouterLine x1={840} y1={218} x2={840} y2={352} active={active === 1} />
          <RouterLine x1={840} y1={218} x2={1420} y2={352} active={active === 2} />
          <div
            style={{
              position: "absolute",
              left: 44,
              right: 44,
              bottom: 44,
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 28,
            }}
          >
            {routes.map((route, index) => (
              <RouteCard
                key={route.name}
                route={route}
                index={index}
                active={active === index}
              />
            ))}
          </div>
        </Panel>
      </div>
    </Base>
  );
};

const DemoScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.demo.duration, 12, 12);
  const shot = f < frame(10)
    ? assets.viewerFruitDone
    : f < frame(20)
      ? assets.viewerMiniwobTarget
      : assets.viewerCanvasCrop;
  return (
    <Base activeIndex={6}>
      <div style={{opacity, height: "100%"}}>
        <Kicker>actual demo surface</Kicker>
        <Title size={78} maxWidth={1340}>
          The viewer shows the tradeoff step by step.
        </Title>
        <div
          style={{
            marginTop: 54,
            display: "grid",
            gridTemplateColumns: "1.16fr 0.84fr",
            gap: 44,
            height: 642,
          }}
        >
          <Capture src={shot} title="running BrowserDelta app capture" />
          <div style={{display: "grid", gridTemplateRows: "1fr 1fr", gap: 24}}>
            <Panel style={{padding: 36}}>
              <div style={{fontFamily: font.mono, color: palette.green, fontSize: 22}}>
                compact observation
              </div>
              <pre
                style={{
                  margin: "24px 0 0",
                  whiteSpace: "pre-wrap",
                  fontFamily: font.mono,
                  fontSize: 29,
                  lineHeight: 1.42,
                  color: palette.ink,
                }}
              >
{`target_hint="faucibus" visible
likely_click_ref=${demoCase.targetRef}
route=text_only
image_sent=false`}
              </pre>
            </Panel>
            <Panel
              style={{
                padding: 36,
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 20,
              }}
            >
              <BigStat value={`${internalDemo.nextActionPredictions}`} label="internal next-action checks" tone="ink" />
              <BigStat value={`${internalDemo.tokenSavingsPct}%`} label="tokens saved in internal demo" tone="green" />
            </Panel>
          </div>
        </div>
      </div>
    </Base>
  );
};

const BenchmarkScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.benchmark.duration, 12, 12);
  const barIn = progress(f, frame(2.0), frame(1.2));
  return (
    <Base activeIndex={7}>
      <div style={{opacity, height: "100%"}}>
        <Kicker>MiniWoB 5-seed eval</Kicker>
        <Title size={76} maxWidth={1420}>
          Near-parity success, about one-sixth the decision context.
        </Title>
        <div
          style={{
            marginTop: 46,
            display: "grid",
            gridTemplateColumns: "0.98fr 1.02fr",
            gap: 42,
            height: 658,
          }}
        >
          <Panel style={{padding: 40}}>
            <ChartTitle title="success rate" subtitle={`${benchmark.seeds} seeds x ${benchmark.tasksPerSeed} tasks`} />
            <Bar
              label="BrowserDelta"
              value={benchmark.compact.successPct}
              max={55}
              suffix="%"
              color={palette.green}
              progress={barIn}
              note={`+/- ${benchmark.compact.successStdPct.toFixed(2)}%`}
            />
            <Bar
              label="full_state"
              value={benchmark.fullState.successPct}
              max={55}
              suffix="%"
              color={palette.blue}
              progress={barIn}
              note={`+/- ${benchmark.fullState.successStdPct.toFixed(2)}%`}
            />
            <div style={{height: 34}} />
            <ChartTitle title="avg decision tokens" subtitle="per episode" />
            <Bar
              label="BrowserDelta"
              value={benchmark.compact.avgTokens}
              max={3200}
              suffix=""
              color={palette.green}
              progress={barIn}
              note={`+/- ${number(benchmark.compact.avgTokensStd)}`}
            />
            <Bar
              label="full_state"
              value={benchmark.fullState.avgTokens}
              max={3200}
              suffix=""
              color={palette.blue}
              progress={barIn}
              note={`+/- ${number(benchmark.fullState.avgTokensStd)}`}
            />
          </Panel>
          <Panel
            style={{
              padding: 42,
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{fontFamily: font.mono, color: palette.green, fontSize: 24}}>
                average token reduction
              </div>
              <div
                style={{
                  marginTop: 22,
                  fontFamily: font.mono,
                  fontSize: 108,
                  lineHeight: 0.95,
                  fontWeight: 800,
                  color: palette.green,
                }}
              >
                {benchmark.tokenReductionPct.toFixed(1)}%
              </div>
              <div style={{marginTop: 18, fontSize: 31, color: palette.ink2}}>
                Compact keeps about{" "}
                {Math.round(
                  (benchmark.compact.successPct / benchmark.fullState.successPct) * 100,
                )}
                % of full-state success while sending far less context.
              </div>
            </div>
            <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18}}>
              <MiniFact label="both success" value={`${benchmark.outcomeClasses.bothSuccess}`} />
              <MiniFact label="compact-only wins" value={`${benchmark.outcomeClasses.compactOnlySuccess}`} />
              <MiniFact label="compact regressions" value={`${benchmark.outcomeClasses.compactRegression}`} tone="red" />
              <MiniFact label="runner errors" value={`${benchmark.outcomeClasses.runnerError}`} tone="ink" />
            </div>
            <div
              style={{
                paddingTop: 18,
                borderTop: `1px solid ${palette.line}`,
                color: palette.muted,
                fontFamily: font.mono,
                fontSize: 19,
              }}
            >
              seed example in VO: {benchmark.seedExample.compactSuccesses}/
              {benchmark.seedExample.tasks} compact vs{" "}
              {benchmark.seedExample.fullStateSuccesses}/{benchmark.seedExample.tasks} full_state
            </div>
          </Panel>
        </div>
      </div>
    </Base>
  );
};

const CloseScene = () => {
  const f = useCurrentFrame();
  const opacity = fade(f, scenes.close.duration, 12, 30);
  const bubbleIn = progress(f, frame(14.2), frame(0.7));
  return (
    <Base activeIndex={8}>
      <div style={{opacity, height: "100%", position: "relative"}}>
        <div style={{position: "absolute", top: 172, left: 0}}>
          <Kicker>BrowserDelta</Kicker>
          <Title size={112} maxWidth={1370}>
            Think changes, not full screenshots.
          </Title>
          <div style={{display: "flex", gap: 16, marginTop: 46}}>
            <StatPill label="fewer decision tokens" value="84.2%" />
            <StatPill label="5-seed MiniWoB" value="625" tone="ink" />
            <StatPill label="near-parity success" value="94%" tone="blue" />
          </div>
        </div>
        <div
          style={{
            position: "absolute",
            right: 18,
            bottom: 88,
            width: 312,
            height: 220,
            borderRadius: 34,
            overflow: "hidden",
            border: `1px solid ${palette.lineDark}`,
            opacity: bubbleIn,
            transform: `translateY(${(1 - bubbleIn) * 28}px)`,
          }}
        >
          <Video src={staticFile(assets.jayIntro)} muted style={{width: "100%", height: "100%", objectFit: "cover"}} />
        </div>
      </div>
    </Base>
  );
};

const LoopNode = ({
  label,
  x,
  y,
  tone,
  active = false,
  style,
}: {
  label: string;
  x?: number;
  y?: number;
  tone: string;
  active?: boolean;
  style?: React.CSSProperties;
}) => (
  <div
    style={{
      position: x === undefined || y === undefined ? "relative" : "absolute",
      left: x,
      top: y,
      width: "100%",
      maxWidth: 206,
      height: 92,
      borderRadius: 22,
      border: `2px solid ${tone}`,
      background: active ? "rgba(180,58,49,0.08)" : "rgba(255,255,255,0.78)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: font.mono,
      fontSize: 23,
      color: tone,
      fontWeight: 700,
      ...style,
    }}
  >
    {label}
  </div>
);

const InlineArrow = () => (
  <div
    style={{
      width: "100%",
      height: 2,
      background: palette.lineDark,
      position: "relative",
    }}
  >
    <div
      style={{
        position: "absolute",
        right: -4,
        top: -5,
        width: 12,
        height: 12,
        borderRight: `2px solid ${palette.lineDark}`,
        borderTop: `2px solid ${palette.lineDark}`,
        transform: "rotate(45deg)",
      }}
    />
  </div>
);

const Arrow = ({
  x,
  y,
  w,
  rotate = 0,
}: {
  x: number;
  y: number;
  w: number;
  rotate?: number;
}) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: w,
      height: 2,
      background: palette.lineDark,
      transform: `rotate(${rotate}deg)`,
      transformOrigin: "left center",
    }}
  >
    <div
      style={{
        position: "absolute",
        right: -4,
        top: -5,
        width: 12,
        height: 12,
        borderRight: `2px solid ${palette.lineDark}`,
        borderTop: `2px solid ${palette.lineDark}`,
        transform: "rotate(45deg)",
      }}
    />
  </div>
);

const MiniFact = ({
  label,
  value,
  tone = "green",
}: {
  label: string;
  value: string;
  tone?: "green" | "red" | "ink";
}) => {
  const color = tone === "red" ? palette.red : tone === "ink" ? palette.ink : palette.green;
  return (
    <div
      style={{
        border: `1px solid ${palette.line}`,
        borderRadius: 18,
        padding: "18px 20px",
        background: palette.paper2,
      }}
    >
      <div style={{fontFamily: font.mono, fontSize: 29, fontWeight: 800, color}}>
        {value}
      </div>
      <div style={{marginTop: 7, color: palette.muted, fontSize: 18}}>{label}</div>
    </div>
  );
};

const LoopCard = ({
  title,
  children,
  faded = false,
}: {
  title: string;
  children: React.ReactNode;
  faded?: boolean;
}) => (
  <Panel
    style={{
      padding: 38,
      opacity: faded ? 0.58 : 1,
      borderColor: faded ? palette.line : palette.green,
    }}
  >
    <div style={{fontFamily: font.mono, fontSize: 23, color: faded ? palette.muted : palette.green}}>
      {title}
    </div>
    <div style={{marginTop: 42}}>{children}</div>
  </Panel>
);

const FlowRow = ({
  items,
  colors,
  emphasisIndex,
  scale = 1,
}: {
  items: string[];
  colors: string[];
  emphasisIndex?: number;
  scale?: number;
}) => (
  <div
    style={{
      display: "grid",
      gridTemplateColumns: "1fr 58px 1fr 58px 1fr",
      alignItems: "center",
      transform: `scale(${scale})`,
      transformOrigin: "center",
    }}
  >
    {items.map((item, index) => (
      <React.Fragment key={item}>
        <div
          style={{
            height: 128,
            borderRadius: 24,
            border: `2px solid ${colors[index]}`,
            background:
              index === emphasisIndex ? "rgba(11,107,43,0.08)" : "rgba(255,255,255,0.76)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: colors[index],
            fontFamily: font.mono,
            fontSize: index === emphasisIndex ? 26 : 23,
            fontWeight: 800,
          }}
        >
          {item}
        </div>
        {index < items.length - 1 ? <div style={{textAlign: "center", fontSize: 34}}>-&gt;</div> : null}
      </React.Fragment>
    ))}
  </div>
);

const Payload = ({label, tone = "green"}: {label: string; tone?: "green" | "red"}) => {
  const color = tone === "red" ? palette.red : palette.green;
  return (
    <div
      style={{
        marginTop: 56,
        border: `1px solid ${color}`,
        borderRadius: 18,
        padding: "20px 22px",
        fontFamily: font.mono,
        fontSize: 24,
        color,
        background: "rgba(255,255,255,0.78)",
      }}
    >
      {label}
    </div>
  );
};

const RegionBox = ({
  left,
  top,
  width,
  height,
  opacity,
}: {
  left: number;
  top: number;
  width: number;
  height: number;
  opacity: number;
}) => (
  <div
    style={{
      position: "absolute",
      left,
      top,
      width,
      height,
      border: `5px solid ${palette.green}`,
      borderRadius: 10,
      opacity,
      boxShadow: "0 0 0 999px rgba(11,107,43,0.03)",
    }}
  />
);

const PipelineStep = ({
  index,
  title,
  body,
  active,
  tone,
}: {
  index: string;
  title: string;
  body: string;
  active: number;
  tone: string;
}) => (
  <div
    style={{
      opacity: 0.25 + active * 0.75,
      transform: `translateY(${(1 - active) * 18}px)`,
      border: `1px solid ${active > 0.5 ? tone : palette.line}`,
      borderRadius: 18,
      padding: "22px 24px",
      marginBottom: 18,
      background: "rgba(255,255,255,0.78)",
    }}
  >
    <div style={{display: "flex", gap: 18, alignItems: "center"}}>
      <div
        style={{
          width: 50,
          height: 50,
          borderRadius: 999,
          background: tone,
          color: palette.paper2,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: font.mono,
          fontSize: 23,
          fontWeight: 800,
        }}
      >
        {index}
      </div>
      <div style={{fontSize: 34, fontWeight: 640}}>{title}</div>
    </div>
    <div style={{marginTop: 12, color: palette.muted, fontSize: 24, lineHeight: 1.22}}>
      {body}
    </div>
  </div>
);

const Gauge = ({
  label,
  value,
  active,
}: {
  label: string;
  value: string;
  active: number;
}) => (
  <div
    style={{
      opacity: active,
      border: `1px solid ${palette.cyan}`,
      borderRadius: 18,
      padding: "20px 22px",
      background: "rgba(24,140,133,0.06)",
    }}
  >
    <div style={{fontFamily: font.mono, color: palette.cyan, fontSize: 42, fontWeight: 800}}>
      {value}
    </div>
    <div style={{fontSize: 19, color: palette.muted}}>{label}</div>
  </div>
);

const RouteCard = ({
  route,
  index,
  active,
  x,
  y,
}: {
  route: {name: string; tone: string; title: string; payload: string};
  index: number;
  active: boolean;
  x?: number;
  y?: number;
}) => {
  const f = useCurrentFrame();
  const appear = progress(f, frame(2.5 + index * 1.0), frame(0.8));
  return (
    <Panel
      style={{
        position: x === undefined || y === undefined ? "relative" : "absolute",
        left: x,
        top: y,
        width: x === undefined || y === undefined ? "auto" : 438,
        height: 214,
        padding: 28,
        borderColor: active ? route.tone : palette.line,
        background: active ? "rgba(255,255,255,0.98)" : "rgba(255,255,255,0.70)",
        opacity: appear,
        transform: `translateY(${(1 - appear) * 24}px) scale(${active ? 1.035 : 1})`,
        transformOrigin: "center",
      }}
    >
      <div style={{fontFamily: font.mono, fontSize: 26, color: route.tone, fontWeight: 800}}>
        {route.name}
      </div>
      <div style={{marginTop: 13, fontSize: 28, lineHeight: 1.08, fontWeight: 640}}>
        {route.title}
      </div>
      <div
        style={{
          marginTop: 14,
          fontFamily: font.mono,
          color: palette.muted,
          fontSize: 17,
          lineHeight: 1.35,
        }}
      >
        {route.payload}
      </div>
    </Panel>
  );
};

const RouterLine = ({
  x1,
  y1,
  x2,
  y2,
  active,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  active: boolean;
}) => {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);
  return (
    <div
      style={{
        position: "absolute",
        left: x1,
        top: y1,
        width: length,
        height: active ? 5 : 2,
        background: active ? palette.green : palette.lineDark,
        transform: `rotate(${angle}deg)`,
        transformOrigin: "left center",
        opacity: active ? 1 : 0.55,
      }}
    />
  );
};

const BigStat = ({
  value,
  label,
  tone,
}: {
  value: string;
  label: string;
  tone: "green" | "ink";
}) => (
  <div>
    <div
      style={{
        fontFamily: font.mono,
        fontSize: 66,
        lineHeight: 1,
        fontWeight: 800,
        color: tone === "green" ? palette.green : palette.ink,
      }}
    >
      {value}
    </div>
    <div style={{marginTop: 12, fontSize: 24, color: palette.muted, lineHeight: 1.2}}>
      {label}
    </div>
  </div>
);

const ChartTitle = ({title, subtitle}: {title: string; subtitle: string}) => (
  <div style={{display: "flex", justifyContent: "space-between", alignItems: "baseline"}}>
    <div style={{fontSize: 34, fontWeight: 650}}>{title}</div>
    <div style={{fontFamily: font.mono, fontSize: 18, color: palette.muted}}>
      {subtitle}
    </div>
  </div>
);

const Bar = ({
  label,
  value,
  max,
  suffix,
  color,
  progress: p,
  note,
}: {
  label: string;
  value: number;
  max: number;
  suffix: string;
  color: string;
  progress: number;
  note: string;
}) => {
  const width = `${(value / max) * 100 * p}%`;
  const digits = value < 100 ? 1 : 0;
  return (
    <div style={{marginTop: 22}}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontFamily: font.mono,
          color: palette.muted,
          fontSize: 19,
        }}
      >
        <span>{label}</span>
        <span>
          {number(value, digits)}
          {suffix} <span style={{color: palette.lineDark}}>{note}</span>
        </span>
      </div>
      <div
        style={{
          marginTop: 8,
          height: 26,
          borderRadius: 999,
          background: "#edf1e9",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width,
            height: "100%",
            borderRadius: 999,
            background: color,
          }}
        />
      </div>
    </div>
  );
};
