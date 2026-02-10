export interface SearchCodeInput {
  query: string;
  topK?: number;
  pathPrefix?: string;
  vector?: number[];
}

export interface AskCodeInput {
  query: string;
  topK?: number;
  pathPrefix?: string;
  language?: string;
  minScore?: number;
  llmModel?: string;
}

export interface OpenFileInput {
  path: string;
  startLine?: number;
  endLine?: number;
  maxBytes?: number;
}

export interface SearchCodeResult {
  score: number;
  path: string;
  startLine: number | null;
  endLine: number | null;
  snippet: string;
}

export interface SearchCodeOutput {
  results: SearchCodeResult[];
  meta: {
    topK: number;
    pathPrefix?: string;
    collection: string;
  };
}

export interface OpenFileOutput {
  path: string;
  startLine: number;
  endLine: number;
  totalLines: number | null;
  text: string;
  truncated: boolean;
}

export interface AskCodeOutput {
  answer: string;
  evidences: SearchCodeResult[];
  meta: {
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
}

export type StdioToolOutput = SearchCodeOutput | OpenFileOutput | AskCodeOutput;

export type StdioErrorCode =
  | 'BAD_REQUEST'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'UNSUPPORTED_MEDIA'
  | 'INTERNAL';

export interface StdioToolRequest {
  id: string;
  tool: string;
  input: unknown;
}

export interface StdioToolSuccessResponse {
  id: string;
  ok: true;
  output: StdioToolOutput;
}

export interface StdioToolErrorResponse {
  id: string;
  ok: false;
  error: {
    code: StdioErrorCode;
    message: string;
  };
}

export type StdioToolResponse =
  | StdioToolSuccessResponse
  | StdioToolErrorResponse;

export interface QdrantSearchHit {
  score?: number;
  payload?: Record<string, unknown>;
}

export interface QdrantSearchResponse {
  result?: QdrantSearchHit[];
}
