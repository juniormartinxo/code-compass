export interface QdrantRuntimeConfig {
  url: string;
  collection: string;
  apiKey?: string;
  timeoutMs: number;
}

const DEFAULT_QDRANT_URL = 'http://localhost:6333';
const DEFAULT_QDRANT_COLLECTION = 'compass__3584__manutic_nomic_embed_code';
const DEFAULT_QDRANT_TIMEOUT_MS = 5000;

export function resolveQdrantConfig(env: NodeJS.ProcessEnv): QdrantRuntimeConfig {
  const collection = env.QDRANT_COLLECTION || DEFAULT_QDRANT_COLLECTION;

  return {
    url: env.QDRANT_URL || DEFAULT_QDRANT_URL,
    collection,
    apiKey: env.QDRANT_API_KEY || undefined,
    timeoutMs: DEFAULT_QDRANT_TIMEOUT_MS,
  };
}
