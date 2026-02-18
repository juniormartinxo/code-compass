export interface QdrantRuntimeConfig {
  url: string;
  collectionBase: string;
  codeCollection: string;
  docsCollection: string;
  apiKey?: string;
  timeoutMs: number;
  rrfK: number;
  diversityFloor: number;
}

const DEFAULT_QDRANT_URL = 'http://localhost:6333';
const DEFAULT_QDRANT_COLLECTION_STEM = 'compass__manutic_nomic_embed';
const DEFAULT_QDRANT_TIMEOUT_MS = 5000;
const DEFAULT_RRF_K = 60;
const DEFAULT_DIVERSITY_FLOOR = 1;

function readPositiveInt(
  value: string | undefined,
  fallback: number,
): number {
  if (!value || !value.trim()) {
    return fallback;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

export function resolveQdrantConfig(env: NodeJS.ProcessEnv): QdrantRuntimeConfig {
  const collectionBase = (env.QDRANT_COLLECTION_BASE || DEFAULT_QDRANT_COLLECTION_STEM).trim();
  const codeCollection = `${collectionBase}__code`;
  const docsCollection = `${collectionBase}__docs`;

  if (!collectionBase) {
    throw new Error('QDRANT_COLLECTION_BASE inválida: valor vazio');
  }
  return {
    url: env.QDRANT_URL || DEFAULT_QDRANT_URL,
    collectionBase,
    codeCollection,
    docsCollection,
    apiKey: env.QDRANT_API_KEY || undefined,
    timeoutMs: DEFAULT_QDRANT_TIMEOUT_MS,
    rrfK: readPositiveInt(env.RRF_K, DEFAULT_RRF_K),
    diversityFloor: readPositiveInt(env.RRF_DIVERSITY_FLOOR, DEFAULT_DIVERSITY_FLOOR),
  };
}
