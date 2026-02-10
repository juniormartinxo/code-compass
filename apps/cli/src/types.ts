export type Evidence = {
  path: string;
  startLine: number | null;
  endLine: number | null;
  score: number;
  snippet: string;
};

export type SearchCodeResult = {
  score: number;
  path: string;
  startLine: number | null;
  endLine: number | null;
  snippet: string;
};

export type SearchCodeResponse = {
  results: SearchCodeResult[];
  meta?: Record<string, unknown>;
};

export type AskCodeMeta = {
  topK: number;
  minScore: number;
  llmModel: string;
  collection: string;
  totalMatches: number;
  contextsUsed: number;
  elapsedMs: number;
  pathPrefix?: string;
  language?: string;
};

export type AskCodeResponse = {
  answer: string;
  evidences: Evidence[];
  meta: AskCodeMeta;
};

export type OpenFileResponse = {
  path: string;
  startLine: number;
  endLine: number;
  totalLines: number | null;
  text: string;
  truncated: boolean;
};

export type AskConfig = {
  topK: number;
  pathPrefix?: string;
  language?: string;
  repo?: string;
  minScore: number;
  debug: boolean;
  llmModel: string;
  mcpCommand: string[];
  requestTimeoutMs: number;
};

export type AskResult = {
  answer: string;
  evidences: Evidence[];
};
