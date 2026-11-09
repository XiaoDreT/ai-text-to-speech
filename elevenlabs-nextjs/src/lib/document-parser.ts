import { StoryboardSegment } from "@/types";
import { normalizeToHmsRange, formatSecondsToHms } from "./timeline-engine";
import * as XLSX from "xlsx";
import mammoth from "mammoth";
import { PDFParse } from "pdf-parse";

// Regex untuk mendeteksi rentang waktu "00:00:00 - 00:00:05" atau "00:00 - 00:05"
const TIME_RANGE_REGEX =
  /\b(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*(?:[-–—~\xad]+|-->|s\/d|sd|sampai|to|hingga|\s+)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\b/i;

export function parseRawTimelineText(
  rawText: string,
  autoGenerateIfNoTimestamps: boolean = true
): StoryboardSegment[] {
  if (!rawText || !rawText.trim()) return [];

  const lines = rawText.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const segments: StoryboardSegment[] = [];

  let currentStart = 0;
  for (const line of lines) {
    // 1. Cek format tabel terpisah pipa (|) atau tab (\t)
    if (line.includes("|") || line.includes("\t")) {
      const sep = line.includes("|") ? "|" : "\t";
      const parts = line.split(sep).map((p) => p.trim());
      if (parts.length >= 2) {
        let tr = parts[0];
        let vis = "";
        let vo = "";

        if (parts.length === 2) {
          vo = parts[1];
        } else {
          vis = parts[1];
          vo = parts.slice(2).join(" ");
        }

        const match = tr.match(TIME_RANGE_REGEX);
        if (match) {
          tr = normalizeToHmsRange(match[0]);
        } else if (autoGenerateIfNoTimestamps) {
          const words = vo.split(" ").length;
          const dur = Math.max(4, Math.round(words / 2.3));
          tr = `${formatSecondsToHms(currentStart, true)} - ${formatSecondsToHms(currentStart + dur, true)}`;
          currentStart += dur + 1;
        }

        if (vo) {
          segments.push({ time_range: tr, visual: vis, text: vo });
          continue;
        }
      }
    }

    // 2. Cek apakah ada time range di awal baris
    const m = line.match(TIME_RANGE_REGEX);
    if (m) {
      const tr = normalizeToHmsRange(m[0]);
      const rest = line.substring(m.index! + m[0].length).replace(/^[:\s\-]+/, "").trim();
      segments.push({
        time_range: tr,
        visual: "",
        text: rest || "Adegan visual berlangsung.",
      });
    } else if (autoGenerateIfNoTimestamps && line.length > 5) {
      const words = line.split(" ").length;
      const dur = Math.max(4, Math.round(words / 2.3));
      const tr = `${formatSecondsToHms(currentStart, true)} - ${formatSecondsToHms(currentStart + dur, true)}`;
      currentStart += dur + 1;
      segments.push({
        time_range: tr,
        visual: "",
        text: line,
      });
    }
  }

  return segments;
}

export async function parseStoryboardBuffer(
  fileName: string,
  buffer: Buffer
): Promise<StoryboardSegment[]> {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";

  // 1. TXT / MD / SRT / VTT / CSV
  if (["txt", "md", "srt", "vtt"].includes(ext)) {
    const text = buffer.toString("utf-8");
    return parseRawTimelineText(text);
  }

  // 2. Excel (.xlsx, .xls, .csv)
  if (["xlsx", "xls", "csv"].includes(ext)) {
    try {
      const workbook = XLSX.read(buffer, { type: "buffer" });
      const firstSheetName = workbook.SheetNames[0];
      const sheet = workbook.Sheets[firstSheetName];
      const rows = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1 });

      const segments: StoryboardSegment[] = [];
      let currentStart = 0;

      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        if (!row || !Array.isArray(row) || row.length === 0) continue;

        // Skip header
        const joined = row.join(" ").toLowerCase();
        if (i === 0 && (joined.includes("estimasi") || joined.includes("waktu") || joined.includes("naskah"))) {
          continue;
        }

        let tr = String(row[0] || "").trim();
        let vis = String(row[1] || "").trim();
        let vo = String(row[2] || "").trim();

        if (!vo && vis) {
          vo = vis;
          vis = "";
        }

        if (!vo && !vis) continue;

        const m = tr.match(TIME_RANGE_REGEX);
        if (m) {
          tr = normalizeToHmsRange(m[0]);
        } else {
          const words = (vo || vis).split(" ").length;
          const dur = Math.max(4, Math.round(words / 2.3));
          tr = `${formatSecondsToHms(currentStart, true)} - ${formatSecondsToHms(currentStart + dur, true)}`;
          currentStart += dur + 1;
        }

        segments.push({ time_range: tr, visual: vis, text: vo });
      }

      if (segments.length > 0) return segments;
    } catch (e) {
      console.error("[parseStoryboardBuffer] Gagal parse Excel:", e);
    }
  }

  // 3. Word (.docx)
  if (ext === "docx") {
    try {
      const result = await mammoth.extractRawText({ buffer });
      return parseRawTimelineText(result.value);
    } catch (e) {
      console.error("[parseStoryboardBuffer] Gagal parse Word .docx:", e);
    }
  }

  // 4. PDF (.pdf)
  if (ext === "pdf") {
    try {
      const parser = new PDFParse({ data: buffer });
      const textData = await parser.getText();
      const rawText = typeof textData === "string" ? textData : (textData?.text || "");
      return parseRawTimelineText(rawText);
    } catch (e) {
      console.error("[parseStoryboardBuffer] Gagal parse PDF:", e);
    }
  }

  // Fallback: decode as utf-8 text
  try {
    return parseRawTimelineText(buffer.toString("utf-8"));
  } catch {
    return [];
  }
}
