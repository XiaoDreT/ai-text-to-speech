import { BASE_URL, DEFAULT_API_KEY, ZEN_PRIMARY_VOICE_ID } from "./constants";
import { Voice, VoiceSetting } from "@/types";

export function getApiKey(): string {
  return (process.env.ELEVENLABS_API_KEY || DEFAULT_API_KEY).trim();
}

export function formatSrtTimestamp(seconds: number): string {
  if (seconds < 0) seconds = 0;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  let millis = Math.round((seconds - Math.floor(seconds)) * 1000);
  if (millis >= 1000) millis = 999;

  const pad = (n: number, w: number = 2) => String(n).padStart(w, "0");
  return `${pad(hours)}:${pad(minutes)}:${pad(secs)},${pad(millis, 3)}`;
}

export interface AlignmentData {
  characters?: string[];
  character_start_times_seconds?: number[];
  character_end_times_seconds?: number[];
}

export function alignmentToSrt(alignment: AlignmentData, maxCharsPerCue: number = 48): string {
  if (!alignment) return "";
  const chars = alignment.characters || [];
  const starts = alignment.character_start_times_seconds || [];
  const ends = alignment.character_end_times_seconds || [];

  if (!chars.length || chars.length !== starts.length || chars.length !== ends.length) {
    return "";
  }

  // 1. Group characters into words with start and end times
  const words: Array<{ text: string; start: number; end: number }> = [];
  let currentWord = "";
  let wordStart: number | null = null;
  let wordEnd: number | null = null;

  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    const st = starts[i];
    const en = ends[i];

    if (/\s/.test(ch)) {
      if (currentWord) {
        words.push({ text: currentWord, start: wordStart ?? st, end: wordEnd ?? en });
        currentWord = "";
        wordStart = null;
        wordEnd = null;
      }
    } else {
      if (wordStart === null) wordStart = st;
      wordEnd = en;
      currentWord += ch;
    }
  }

  if (currentWord) {
    words.push({ text: currentWord, start: wordStart ?? 0, end: wordEnd ?? 0 });
  }

  if (!words.length) return "";

  // 2. Group words into cues
  const cues: Array<{ text: string; start: number; end: number }> = [];
  let currentWords: Array<{ text: string; start: number; end: number }> = [];
  let currentLen = 0;

  for (const w of words) {
    const wText = w.text;
    if (currentWords.length && currentLen + 1 + wText.length > maxCharsPerCue) {
      cues.push({
        text: currentWords.map((x) => x.text).join(" "),
        start: currentWords[0].start,
        end: currentWords[currentWords.length - 1].end,
      });
      currentWords = [w];
      currentLen = wText.length;
    } else {
      currentWords.push(w);
      currentLen += (currentLen > 0 ? 1 : 0) + wText.length;
    }

    if (/[.!?]$/.test(wText) && currentLen >= 18) {
      cues.push({
        text: currentWords.map((x) => x.text).join(" "),
        start: currentWords[0].start,
        end: currentWords[currentWords.length - 1].end,
      });
      currentWords = [];
      currentLen = 0;
    }
  }

  if (currentWords.length) {
    cues.push({
      text: currentWords.map((x) => x.text).join(" "),
      start: currentWords[0].start,
      end: currentWords[currentWords.length - 1].end,
    });
  }

  // 3. Output SRT format string
  return cues
    .map((cue, idx) => {
      const s = formatSrtTimestamp(cue.start);
      const e = formatSrtTimestamp(cue.end);
      return `${idx + 1}\n${s} --> ${e}\n${cue.text}\n`;
    })
    .join("\n");
}

export async function fetchVoices(apiKey?: string): Promise<Voice[]> {
  const key = apiKey || getApiKey();
  const res = await fetch(`${BASE_URL}/voices`, {
    headers: { "xi-api-key": key },
    next: { revalidate: 30 },
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Gagal mengambil data suara (${res.status}): ${errText}`);
  }

  const data = await res.json();
  const voices: Voice[] = data.voices || [];

  // Prioritize Zen (3OAL9h0y2edOwGJbMU4X) at index 0, then cloned, then id language, then others
  voices.sort((a, b) => {
    const isZenA = a.voice_id === ZEN_PRIMARY_VOICE_ID || a.name?.toLowerCase() === "zen";
    const isZenB = b.voice_id === ZEN_PRIMARY_VOICE_ID || b.name?.toLowerCase() === "zen";
    if (isZenA && !isZenB) return -1;
    if (!isZenA && isZenB) return 1;

    const rankCat = (v: Voice) => {
      if (v.category === "cloned") return 1;
      if (v.category === "generated") return 2;
      if (v.category === "professional") return 3;
      return 4;
    };
    const rankA = rankCat(a);
    const rankB = rankCat(b);
    if (rankA !== rankB) return rankA - rankB;

    const langA = a.labels?.language === "id" ? 0 : 1;
    const langB = b.labels?.language === "id" ? 0 : 1;
    if (langA !== langB) return langA - langB;

    return (a.name || "").localeCompare(b.name || "");
  });

  return voices;
}

export async function fetchModels(apiKey?: string) {
  const key = apiKey || getApiKey();
  const res = await fetch(`${BASE_URL}/models`, {
    headers: { "xi-api-key": key },
    next: { revalidate: 300 },
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Gagal mengambil model (${res.status}): ${errText}`);
  }

  const data = await res.json();
  return (data || []).filter((m: { can_do_text_to_speech?: boolean }) => m.can_do_text_to_speech !== false);
}

export interface GenerateSpeechOptions {
  text: string;
  voiceId?: string;
  modelId?: string;
  stability?: number;
  similarityBoost?: number;
  style?: number;
  speed?: number;
  useSpeakerBoost?: boolean;
  outputFormat?: string;
  languageCode?: string;
  previousText?: string;
  nextText?: string;
  withTimestamps?: boolean;
  apiKey?: string;
}

export async function generateSpeechRaw(options: GenerateSpeechOptions): Promise<{
  audioBuffer: Buffer;
  mimeType: string;
  extension: string;
  alignment?: AlignmentData;
  srtContent?: string;
}> {
  const key = options.apiKey || getApiKey();
  const voiceId = options.voiceId || ZEN_PRIMARY_VOICE_ID;
  const endpointSuffix = options.withTimestamps ? "/with-timestamps" : "";
  const outputFormat = options.outputFormat || "mp3_44100_128";

  const url = `${BASE_URL}/text-to-speech/${voiceId}${endpointSuffix}?output_format=${outputFormat}`;

  const voiceSettings: VoiceSetting = {
    stability: Number((options.stability ?? 0.55).toFixed(2)),
    similarity_boost: Number((options.similarityBoost ?? 0.8).toFixed(2)),
    style: Number((options.style ?? 0.0).toFixed(2)),
    use_speaker_boost: options.useSpeakerBoost !== false,
    speed: Number((options.speed ?? 1.0).toFixed(2)),
  };

  const payload: Record<string, unknown> = {
    text: options.text,
    model_id: options.modelId || "eleven_multilingual_v2",
    voice_settings: voiceSettings,
    apply_text_normalization: "auto",
  };

  if (options.languageCode && options.languageCode !== "auto") {
    payload.language_code = options.languageCode;
  }
  if (options.previousText?.trim()) {
    payload.previous_text = options.previousText.trim();
  }
  if (options.nextText?.trim()) {
    payload.next_text = options.nextText.trim();
  }

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "xi-api-key": key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errText = await res.text();
    let detail = errText;
    try {
      const errJson = JSON.parse(errText);
      detail = errJson.detail?.message || errJson.detail || errText;
    } catch {
      // keep raw string
    }
    throw new Error(`ElevenLabs API Error (${res.status}): ${detail}`);
  }

  if (options.withTimestamps) {
    const json = await res.json();
    const audioB64 = json.audio_base64 || "";
    const audioBuffer = Buffer.from(audioB64, "base64");
    const alignment = json.alignment || json.normalized_alignment;
    const srtContent = alignment ? alignmentToSrt(alignment) : "";
    return {
      audioBuffer,
      mimeType: outputFormat.startsWith("pcm_") ? "audio/wav" : "audio/mpeg",
      extension: outputFormat.startsWith("pcm_") ? "wav" : "mp3",
      alignment,
      srtContent,
    };
  }

  const arrayBuffer = await res.arrayBuffer();
  const audioBuffer = Buffer.from(arrayBuffer);
  return {
    audioBuffer,
    mimeType: outputFormat.startsWith("pcm_") ? "audio/wav" : "audio/mpeg",
    extension: outputFormat.startsWith("pcm_") ? "wav" : "mp3",
  };
}
