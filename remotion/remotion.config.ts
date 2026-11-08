import { Config } from "@remotion/cli/config";

// Rendering is driven by socialauto (Python); these are only defaults for a manual `npx remotion studio`.
Config.setVideoImageFormat("jpeg");
Config.setConcurrency(1);          // law 9: this machine has 7.4 GB
