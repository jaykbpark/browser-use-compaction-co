export const transcript = {
  durationSeconds: 208.604,
  source: "video/work/jay-input/transcript/audio.tsv",
};

export const benchmark = {
  tasksPerSeed: 125,
  seeds: 5,
  episodes: 625,
  compact: {
    label: "BrowserDelta",
    successPct: 40.96,
    successStdPct: 1.55,
    avgTokens: 469.88,
    avgTokensStd: 28.3,
  },
  fullState: {
    label: "full_state",
    successPct: 43.52,
    successStdPct: 1.93,
    avgTokens: 2978.32,
    avgTokensStd: 212.0,
  },
  tokenReductionPct: 84.17,
  tokenReductionStdPct: 1.16,
  outcomeClasses: {
    bothSuccess: 238,
    compactOnlySuccess: 18,
    compactRegression: 34,
    bothFailed: 335,
    runnerError: 0,
  },
  seedExample: {
    compactSuccesses: 46,
    fullStateSuccesses: 50,
    tasks: 125,
  },
  source:
    "reports/demo/miniwob-5seed-summary/summary.json",
};

export const internalDemo = {
  nextActionPredictions: 12,
  tokenSavingsPct: 76,
  parityLabel: "matched full-state next-action baseline",
};

export const demoCase = {
  task: "find and click \"faucibus\"",
  env: "browsergym/miniwob.click-collapsible-2",
  compactTokens: 857,
  fullStateTokens: 2174,
  targetRef: "28",
};

export const assets = {
  voiceover: "private/jay-voiceover.wav",
  jayIntro: "private/jay-intro.mp4",
  viewerFruitStart: "assets/app/viewer-fruit-step1.png",
  viewerFruitDone: "assets/app/viewer-fruit-step4.png",
  viewerCanvasCrop: "assets/app/viewer-canvas-step2.png",
  viewerMiniwobTarget: "assets/app/viewer-miniwob-collapsible-step4.png",
  codecReference: "assets/app/codec-reference.png",
};
