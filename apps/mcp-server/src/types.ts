export type Scope =
  | {
      type: 'repo';
      repo: string;
    }
  | {
      type: 'repos';
      repos: string[];
    }
  | {
      type: 'all';
    };

export interface ScopeMeta {
  type: 'repo' | 'repos' | 'all';
  repos?: string[];
}

export interface ResolvedScope {
  type: 'repo' | 'repos' | 'all';
  repos: string[];
}

export type ContentType = 'code' | 'docs' | 'all';

export type CollectionContentType = Exclude<ContentType, 'all'>;

export type CollectionStatus = 'ok' | 'partial' | 'unavailable';

export interface CollectionMeta {
  name: string;
  contentType: CollectionContentType;
  hits: number;
  latencyMs: number;
  status: CollectionStatus;
}

export interface SearchCodeInput {
  repo?: string;
  scope?: Scope;
  query: string;
  topK?: number;
  pathPrefix?: string;
  vector?: number[];
  contentType?: ContentType;
  strict?: boolean;
}

export interface AskCodeInput {
  repo?: string;
  scope?: Scope;
  query: string;
  topK?: number;
  pathPrefix?: string;
  language?: string;
  minScore?: number;
  llmModel?: string;
  grounded?: boolean;
  contentType?: ContentType;
  strict?: boolean;
}

export interface OpenFileInput {
  repo: string;
  path: string;
  startLine?: number;
  endLine?: number;
  maxBytes?: number;
}

export interface SearchCodeResult {
  repo: string;
  score: number;
  path: string;
  startLine: number | null;
  endLine: number | null;
  snippet: string;
  contentType: CollectionContentType;
}

export interface SearchCodeOutput {
  results: SearchCodeResult[];
  meta: {
    repo?: string;
    scope: ScopeMeta;
    topK: number;
    pathPrefix?: string;
    contentType: ContentType;
    strict: boolean;
    collections: CollectionMeta[];
    /**
     * @deprecated Use `meta.collections` para ler as coleções consultadas.
     */
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
    repo?: string;
    scope: ScopeMeta;
    topK: number;
    minScore: number;
    llmModel: string;
    contentType: ContentType;
    strict: boolean;
    collections: CollectionMeta[];
    /**
     * @deprecated Use `meta.collections` para ler as coleções consultadas.
     */
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
  | 'INTERNAL'
  | 'EMBEDDING_FAILED'
  | 'EMBEDDING_INVALID'
  | 'QDRANT_UNAVAILABLE'
  | 'CHAT_FAILED';

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

export interface QdrantSearchOutput {
  hits: QdrantSearchHit[];
  collection: string;
  collections: CollectionMeta[];
}
