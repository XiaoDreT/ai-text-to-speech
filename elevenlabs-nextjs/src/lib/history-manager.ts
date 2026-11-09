import fs from "fs";
import path from "path";
import { HistoryItem } from "@/types";

const OUTPUT_DIR = path.join(process.cwd(), "outputs");
const HISTORY_FILE = path.join(OUTPUT_DIR, "history.json");

function ensureOutputDir() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }
}

export function getHistory(): HistoryItem[] {
  ensureOutputDir();
  if (!fs.existsSync(HISTORY_FILE)) {
    return [];
  }
  try {
    const raw = fs.readFileSync(HISTORY_FILE, "utf-8");
    const data = JSON.parse(raw);
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export function saveHistoryItem(item: HistoryItem): void {
  ensureOutputDir();
  const current = getHistory();
  current.unshift(item);
  const trimmed = current.slice(0, 100); // retain last 100 items
  try {
    fs.writeFileSync(HISTORY_FILE, JSON.stringify(trimmed, null, 2), "utf-8");
  } catch (e) {
    console.error("[saveHistoryItem] Error saving history:", e);
  }
}

export function clearHistory(): void {
  ensureOutputDir();
  try {
    if (fs.existsSync(HISTORY_FILE)) {
      fs.unlinkSync(HISTORY_FILE);
    }
  } catch (e) {
    console.error("[clearHistory] Error clearing history:", e);
  }
}

export function saveOutputFile(fileName: string, data: Buffer | string): string {
  ensureOutputDir();
  const filePath = path.join(OUTPUT_DIR, fileName);
  fs.writeFileSync(filePath, data);
  return filePath;
}

export function getOutputFilePath(fileName: string): string | null {
  const filePath = path.join(OUTPUT_DIR, fileName);
  if (fs.existsSync(filePath)) {
    return filePath;
  }
  return null;
}
