import {Composition} from "remotion";
import {
  BrowserDeltaDemo,
  DURATION_IN_FRAMES,
  FPS,
  HEIGHT,
  WIDTH,
} from "./BrowserDeltaDemo";

export const RemotionRoot = () => {
  return (
    <Composition
      id="BrowserDeltaDemo"
      component={BrowserDeltaDemo}
      durationInFrames={DURATION_IN_FRAMES}
      fps={FPS}
      height={HEIGHT}
      width={WIDTH}
    />
  );
};
