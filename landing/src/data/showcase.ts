export interface ShowcaseVideo {
  id: string;
  title: string;
  videoId: string;
  start?: number;
}

export const showcaseVideos: ShowcaseVideo[] = [
  {
    id: "demo-1",
    title: "Andro-DLS — Device Exploitation Demo",
    videoId: "nPcq7zsgeKw",
  },
  {
    id: "demo-2",
    title: "Andro-DLS — Control & Data Extraction Demo",
    videoId: "R46HFvBMtJM",
  },
  {
    id: "demo-3",
    title: "Andro-DLS — Overview",
    videoId: "xDfHKB3NdTg",
  },
];
