export interface VoiceSetting {
  stability: number;
  similarity_boost: number;
  style: number;
  use_speaker_boost: boolean;
  speed: number;
}

export interface Voice {
  voice_id: string;
  name: string;
  category: "cloned" | "professional" | "premade" | "generated" | string;
  description?: string;
  preview_url?: string;
  labels?: Record<string, string>;
  settings?: VoiceSetting;
}

export interface Model {
  model_id: string;
  name: string;
  description: string;
  can_do_text_to_speech?: boolean;
  languages?: Array<{ language_id: string; name: string }>;
}

export interface StoryboardSegment {
  time_range: string;
  visual: string;
  text: string;
}

export interface DialogueLine {
  voice_id: string;
  voice_name?: string;
  text: string;
}

export interface HistoryItem {
  id: string;
  timestamp: string;
  mode: "single_tts" | "dialog" | "timeline_tts";
  voice_id: string;
  voice_name: string;
  feature_name?: string;
  model_id: string;
  text: string;
  settings?: VoiceSetting;
  output_format?: string;
  audio_url?: string;
  srt_url?: string;
  video_url?: string;
  size_bytes?: number;
  elapsed_sec?: number;
  segments?: Array<{
    index: number;
    voice_name: string;
    text: string;
  }>;
}

export type FitMode = "natural_pad" | "auto_fit" | "strict_trim";
export type SubtitleStyle = "outline" | "shaded_box" | "yellow_outline";
