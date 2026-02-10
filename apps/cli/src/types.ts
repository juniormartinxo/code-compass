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
  debug: boolean;
  ollamaUrl: string;
  embeddingModel: string;
  llmModel: string;
  mcpCommand: string[];
  requestTimeoutMs: number;
};

export type AskResult = {
  answer: string;
  evidences: Evidence[];
};
