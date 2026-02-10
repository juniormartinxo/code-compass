import fs from "node:fs";
import path from "node:path";

export type ParsedCommand = {
  command: string;
  args: string[];
};

export type EvidenceCandidate = {
  path: string;
  startLine: number | null;
  endLine: number | null;
  score: number;
  snippet: string;
};

export type EvidenceSelection = {
  all: EvidenceCandidate[];
  visible: EvidenceCandidate[];
};

export function parseCommandLine(commandLine: string): ParsedCommand {
  const parts: string[] = [];
  let current = "";
  let quote: "'" | '"' | null = null;

  for (let i = 0; i < commandLine.length; i += 1) {
    const char = commandLine[i];

    if (quote) {
      if (char === quote) {
        quote = null;
      } else if (char === "\\" && i + 1 < commandLine.length) {
        current += commandLine[i + 1];
        i += 1;
      } else {
        current += char;
      }
      continue;
    }

    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }

    if (char === " ") {
      if (current) {
        parts.push(current);
        current = "";
      }
      continue;
    }

    current += char;
  }

  if (current) {
    parts.push(current);
  }

  if (parts.length === 0) {
    throw new Error("Comando MCP vazio");
  }

  return { command: parts[0], args: parts.slice(1) };
}

export function findRepoRoot(startDir: string): string | null {
  let current = path.resolve(startDir);
  const root = path.parse(current).root;

  while (true) {
    const pnpmWorkspace = path.join(current, "pnpm-workspace.yaml");
    const gitDir = path.join(current, ".git");
    if (fs.existsSync(pnpmWorkspace) || fs.existsSync(gitDir)) {
      return current;
    }

    if (current === root) {
      return null;
    }

    current = path.dirname(current);
  }
}

export function isSafeRelativePath(value: string): boolean {
  if (!value) return false;
  if (value.includes("\u0000")) return false;
  if (path.isAbsolute(value)) return false;
  if (value.includes("..")) return false;
  if (/^[A-Za-z]:\\/.test(value)) return false;
  return true;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function formatLines(startLine: number | null, endLine: number | null): string {
  if (!startLine && !endLine) return "?";
  const start = startLine ?? "?";
  const end = endLine ?? "?";
  return `${start}-${end}`;
}

export function splitSnippet(snippet: string, maxLines: number): string {
  const lines = snippet.replace(/\r\n/g, "\n").split("\n");
  if (lines.length <= maxLines) {
    return lines.join("\n");
  }
  return [...lines.slice(0, maxLines), "..."].join("\n");
}

export function normalizeLanguageInput(value?: string): string | undefined {
  if (!value) return undefined;
  return value.trim().toLowerCase();
}

const LANGUAGE_EXTENSIONS: Record<string, string[]> = {
  ts: [".ts", ".tsx"],
  tsx: [".tsx"],
  js: [".js", ".jsx"],
  jsx: [".jsx"],
  py: [".py"],
  md: [".md"],
  json: [".json"],
  yaml: [".yaml", ".yml"],
  yml: [".yml", ".yaml"],
  txt: [".txt"],
};

export function matchesLanguage(pathValue: string, language?: string): boolean {
  if (!language) return true;
  const normalized = normalizeLanguageInput(language);
  if (!normalized) return true;

  if (normalized.startsWith(".")) {
    return pathValue.toLowerCase().endsWith(normalized);
  }

  const exts = LANGUAGE_EXTENSIONS[normalized];
  if (!exts) {
    return pathValue.toLowerCase().endsWith(`.${normalized}`);
  }

  return exts.some((ext) => pathValue.toLowerCase().endsWith(ext));
}

export function hasUsableSnippet(snippet: string): boolean {
  const normalized = snippet.trim().toLowerCase();
  if (!normalized) return false;
  return normalized !== "(no snippet)";
}

export function curateEvidences(
  evidences: EvidenceCandidate[],
  options: { minScore: number; maxVisible: number },
): EvidenceSelection {
  const all = [...evidences].sort((left, right) => right.score - left.score);
  const visible: EvidenceCandidate[] = [];
  const seenPaths = new Set<string>();

  for (const evidence of all) {
    if (evidence.score < options.minScore) {
      continue;
    }
    if (!hasUsableSnippet(evidence.snippet)) {
      continue;
    }
    if (seenPaths.has(evidence.path)) {
      continue;
    }

    visible.push(evidence);
    seenPaths.add(evidence.path);

    if (visible.length >= options.maxVisible) {
      break;
    }
  }

  return { all, visible };
}
