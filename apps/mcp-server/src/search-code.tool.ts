import { Injectable } from '@nestjs/common';

import { ToolInputError } from './errors';
import { resolveScope } from './scope';
import { QdrantService } from './qdrant.service';
import { ContentType, QdrantSearchHit, ResolvedScope, SearchCodeInput, SearchCodeOutput } from './types';

const DEFAULT_TOP_K = 10;
const MIN_TOP_K = 1;
const MAX_TOP_K = 20;
const MAX_QUERY_CHARS = 500;
const MAX_PATH_PREFIX_CHARS = 200;
const MAX_SNIPPET_CHARS = 300;
const MIN_SNIPPET_CHARS = 200;
const MAX_PER_REPO_ON_ALL_SCOPE = 3;

type ValidatedSearchInput = {
  scope: ResolvedScope;
  query: string;
  topK: number;
  pathPrefix: string;
  vector: number[];
  contentType: ContentType;
  strict: boolean;
};

@Injectable()
export class SearchCodeTool {
  constructor(private readonly qdrantService: QdrantService) {}

  async execute(rawInput: unknown): Promise<SearchCodeOutput> {
    const input = this.validateInput(rawInput);
    const searchOutput = await this.qdrantService.searchPoints({
      vector: input.vector,
      topK: input.topK,
      pathPrefix: input.pathPrefix,
      repos: input.scope.type === 'all' ? undefined : input.scope.repos,
      contentType: input.contentType,
      strict: input.strict,
    });

    const mapped = searchOutput.hits.map((hit) => this.mapHitToResult(hit));
    const results = this.applyScopeResultGuards(mapped, input.scope, input.topK);

    const meta: SearchCodeOutput['meta'] = {
      scope: this.toScopeMeta(input.scope),
      topK: input.topK,
      collection: searchOutput.collection,
      collections: searchOutput.collections,
      contentType: input.contentType,
      strict: input.strict,
    };

    if (input.scope.type === 'repo') {
      meta.repo = input.scope.repos[0];
    }

    if (input.pathPrefix) {
      meta.pathPrefix = input.pathPrefix;
    }

    return {
      results,
      meta,
    };
  }

  private validateInput(rawInput: unknown): ValidatedSearchInput {
    if (!rawInput || typeof rawInput !== 'object') {
      throw new ToolInputError('Input inválido: esperado objeto');
    }

    const input = rawInput as SearchCodeInput;
    const scope = resolveScope({
      scope: input.scope,
      repo: input.repo,
    }, process.env);
    const query = this.validateQuery(input.query);
    const topK = this.clampTopK(input.topK);
    const pathPrefix = this.validatePathPrefix(input.pathPrefix);
    const vector = this.validateVector(input.vector);
    const contentType = this.validateContentType(input.contentType);
    const strict = this.validateStrict(input.strict);

    return {
      scope,
      query,
      topK,
      pathPrefix,
      vector,
      contentType,
      strict,
    };
  }

  private validateQuery(query: unknown): string {
    if (typeof query !== 'string') {
      throw new ToolInputError('Campo "query" deve ser string');
    }
    const normalized = query.trim();
    if (!normalized) {
      throw new ToolInputError('Campo "query" é obrigatório e não pode ser vazio');
    }
    if (normalized.length > MAX_QUERY_CHARS) {
      throw new ToolInputError(`Campo "query" deve ter no máximo ${MAX_QUERY_CHARS} caracteres`);
    }
    return normalized;
  }

  private clampTopK(topK: unknown): number {
    if (topK === undefined || topK === null) {
      return DEFAULT_TOP_K;
    }

    if (typeof topK !== 'number' || Number.isNaN(topK)) {
      throw new ToolInputError('Campo "topK" deve ser number');
    }

    return Math.min(MAX_TOP_K, Math.max(MIN_TOP_K, Math.trunc(topK)));
  }

  private validatePathPrefix(pathPrefix: unknown): string {
    if (pathPrefix === undefined || pathPrefix === null) {
      return '';
    }
    if (typeof pathPrefix !== 'string') {
      throw new ToolInputError('Campo "pathPrefix" deve ser string');
    }
    const normalized = pathPrefix.trim();
    if (normalized.length > MAX_PATH_PREFIX_CHARS) {
      throw new ToolInputError(
        `Campo "pathPrefix" deve ter no máximo ${MAX_PATH_PREFIX_CHARS} caracteres`,
      );
    }
    if (normalized.includes('\0') || normalized.includes('..')) {
      throw new ToolInputError('Campo "pathPrefix" contém sequência inválida');
    }
    return normalized;
  }

  private validateVector(vector: unknown): number[] {
    if (!Array.isArray(vector)) {
      throw new ToolInputError(
        'Campo "vector" é obrigatório neste ambiente. Configure embeddings no Node ou envie o vetor da query.',
      );
    }
    if (vector.length === 0) {
      throw new ToolInputError('Campo "vector" não pode ser vazio');
    }
    if (!vector.every((item) => typeof item === 'number' && Number.isFinite(item))) {
      throw new ToolInputError('Campo "vector" deve conter apenas numbers finitos');
    }
    return vector;
  }

  private validateContentType(contentType: unknown): ContentType {
    if (contentType === undefined || contentType === null) {
      return 'all';
    }
    if (contentType !== 'code' && contentType !== 'docs' && contentType !== 'all') {
      throw new ToolInputError('Campo "contentType" deve ser "code", "docs" ou "all"');
    }
    return contentType;
  }

  private validateStrict(strict: unknown): boolean {
    if (strict === undefined || strict === null) {
      return false;
    }
    if (typeof strict !== 'boolean') {
      throw new ToolInputError('Campo "strict" deve ser boolean');
    }
    return strict;
  }

  private mapHitToResult(hit: QdrantSearchHit) {
    const payload = this.ensurePayload(hit.payload);
    const snippet = this.extractSnippet(payload);

    return {
      repo: this.ensureRepo(payload.repo),
      score: this.ensureScore(hit.score),
      path: this.ensurePath(payload.path),
      startLine: this.toNumberOrNull(payload.startLine ?? payload.start_line),
      endLine: this.toNumberOrNull(payload.endLine ?? payload.end_line),
      snippet,
      contentType: this.ensureContentType(payload.content_type, payload.path),
    };
  }

  private ensurePayload(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object') {
      return {};
    }
    return payload as Record<string, unknown>;
  }

  private ensureScore(score: unknown): number {
    if (typeof score !== 'number' || Number.isNaN(score)) {
      return 0;
    }
    return score;
  }

  private ensurePath(path: unknown): string {
    if (typeof path !== 'string' || !path.trim()) {
      return '(unknown path)';
    }
    const normalized = path.trim();
    return normalized.length > MAX_PATH_PREFIX_CHARS
      ? normalized.slice(0, MAX_PATH_PREFIX_CHARS)
      : normalized;
  }

  private ensureRepo(repo: unknown): string {
    if (typeof repo !== 'string') {
      return '(unknown)';
    }
    const normalized = repo.trim();
    return normalized || '(unknown)';
  }

  private toNumberOrNull(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return Math.trunc(value);
    }
    return null;
  }

  private ensureContentType(contentType: unknown, path: unknown): 'code' | 'docs' {
    if (contentType === 'code' || contentType === 'docs') {
      return contentType;
    }
    if (typeof path === 'string') {
      const normalized = path.toLowerCase();
      if (normalized.endsWith('.md') || normalized.endsWith('.mdx') || normalized.includes('/docs/')) {
        return 'docs';
      }
    }
    return 'code';
  }

  private extractSnippet(payload: Record<string, unknown>): string {
    const candidate = payload.text;
    if (typeof candidate !== 'string') {
      return '(no snippet)';
    }
    const normalized = candidate.replace(/\s+/g, ' ').trim();
    if (!normalized) {
      return '(no snippet)';
    }

    if (normalized.length <= MAX_SNIPPET_CHARS) {
      return normalized;
    }

    const targetLength = Math.max(MIN_SNIPPET_CHARS, MAX_SNIPPET_CHARS - 3);
    return `${normalized.slice(0, targetLength).trimEnd()}...`;
  }

  private applyScopeResultGuards(
    results: SearchCodeOutput['results'],
    scope: ResolvedScope,
    topK: number,
  ): SearchCodeOutput['results'] {
    if (scope.type !== 'all') {
      return results.slice(0, topK);
    }

    const accepted: SearchCodeOutput['results'] = [];
    const perRepoCounter = new Map<string, number>();

    for (const result of results) {
      const currentCount = perRepoCounter.get(result.repo) ?? 0;
      if (currentCount >= MAX_PER_REPO_ON_ALL_SCOPE) {
        continue;
      }

      accepted.push(result);
      perRepoCounter.set(result.repo, currentCount + 1);

      if (accepted.length >= topK) {
        break;
      }
    }

    return accepted;
  }

  private toScopeMeta(scope: ResolvedScope): SearchCodeOutput['meta']['scope'] {
    if (scope.type === 'all') {
      return { type: 'all' };
    }

    if (scope.type === 'repo') {
      return {
        type: 'repo',
        repos: [...scope.repos],
      };
    }

    return {
      type: 'repos',
      repos: [...scope.repos],
    };
  }
}
