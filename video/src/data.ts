export const benchmark = {
  tasks: 125,
  compact: {
    label: "BrowserDelta compact",
    successes: 48,
    successRate: 0.384,
    avgTokens: 451.7,
  },
  fullState: {
    label: "full_state baseline",
    successes: 50,
    successRate: 0.4,
    avgTokens: 2828.4,
  },
  tokenReductionPct: 84.0,
  sameResultTasks: 105,
  compactOnlyWins: 5,
  compactRegressions: 5,
  runnerErrors: 10,
};

export const demoCase = {
  task: "find and click \"faucibus\"",
  env: "browsergym/miniwob.click-collapsible-2",
  compactTokens: 1162,
  fullStateTokens: 2662,
  compactResult: "1/1",
  fullStateResult: "0/1",
  targetRef: "28",
};

export const assets = {
  standardLoop: "assets/standard-loop.png",
  browserDeltaLoop: "assets/browserdelta-loop.png",
  visualDeltaPolicy: "assets/visualdelta-policy.png",
  targetFound: "assets/demo-target-found.png",
  viewerUi: "assets/viewer-ui.png",
  compactObservation: "assets/compact-observation.png",
  benchmark125: "assets/benchmark-125.png",
};
