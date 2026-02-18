import { Injectable } from '@nestjs/common';
import axios from 'axios';

import { OpenFileTool } from './open-file.tool';
import { SearchCodeTool } from './search-code.tool';
import { ToolInputError, ToolExecutionError } from './errors';
import { resolveScope } from './scope';
import { AskCodeInput, AskCodeOutput, ContentType, ResolvedScope, SearchCodeResult } from './types';

const DEFAULT_TOP_K = 5;
const MIN_TOP_K = 1;
const MAX_TOP_K = 20;
const MAX_QUERY_CHARS = 500;
const MAX_PATH_PREFIX_CHARS = 200;
const MAX_LANGUAGE_CHARS = 32;
const DEFAULT_MIN_SCORE = 0.6;
const DEFAULT_OLLAMA_URL = 'http://localhost:11434';
const DEFAULT_EMBEDDING_MODEL = 'manutic/nomic-embed-code';
const DEFAULT_LLM_MODEL = 'gpt-oss:latest';
const DEFAULT_TIMEOUT_MS = 120_000;
const MAX_CONTEXTS_PER_REPO_WIDE_SCOPE = 2;

const LANGUAGE_EXTENSIONS: Record<string, string[]> = {
  ts: ['.ts', '.tsx'],
  tsx: ['.tsx'],
  js: ['.js', '.jsx'],
  jsx: ['.jsx'],
  py: ['.py'],
  md: ['.md'],
  json: ['.json'],
  yaml: ['.yaml', '.yml'],
  yml: ['.yml', '.yaml'],
  txt: ['.txt'],
};

type ValidatedAskInput = {
  scope: ResolvedScope;
  query: string;
  topK: number;
  pathPrefix: string;
  language: string;
  minScore: number;
  llmModel: string;
  grounded: boolean;
  contentType: ContentType;
  strict: boolean;
};

@Injectable()
export class AskCodeTool {
  constructor(
    private readonly searchCodeTool: SearchCodeTool,
    private readonly openFileTool: OpenFileTool,
  ) {}

  async execute(rawInput: unknown): Promise<AskCodeOutput> {
    const startedAt = Date.now();
    const input = this.validateInput(rawInput);

    const vector = await this.embedQuestion(input.query);
    const searchOutput = await this.searchCodeTool.execute({
      scope: this.toScopeInput(input.scope),
      query: input.query,
      topK: input.topK,
      pathPrefix: input.pathPrefix,
      vector,
      contentType: input.contentType,
      strict: input.strict,
    });

    const ranked = searchOutput.results
      .filter((result) => this.matchesLanguage(result.path, input.language))
      .filter((result) => result.score >= input.minScore)
      .slice(0, input.topK);

    const enriched = await this.enrichEvidences(input.scope, ranked);

    if (enriched.length === 0) {
      return {
        answer: 'Sem evidencia suficiente. Tente refinar a pergunta ou ajustar os filtros.',
        evidences: [],
        meta: {
          scope: this.toScopeMeta(input.scope),
          topK: input.topK,
          minScore: input.minScore,
          llmModel: input.llmModel,
          contentType: input.contentType,
          strict: input.strict,
          repo: input.scope.type === 'repo' ? input.scope.repos[0] : undefined,
          collection: searchOutput.meta.collection,
          collections: searchOutput.meta.collections,
          totalMatches: searchOutput.results.length,
          contextsUsed: 0,
          elapsedMs: Date.now() - startedAt,
          pathPrefix: input.pathPrefix || undefined,
          language: input.language || undefined,
        },
      };
    }

    if (input.grounded) {
      const answer = this.buildGroundedAnswer(enriched);
      return {
        answer,
        evidences: enriched,
        meta: {
          scope: this.toScopeMeta(input.scope),
          topK: input.topK,
          minScore: input.minScore,
          llmModel: input.llmModel,
          contentType: input.contentType,
          strict: input.strict,
          repo: input.scope.type === 'repo' ? input.scope.repos[0] : undefined,
          collection: searchOutput.meta.collection,
          collections: searchOutput.meta.collections,
          totalMatches: searchOutput.results.length,
          contextsUsed: enriched.length,
          elapsedMs: Date.now() - startedAt,
          pathPrefix: input.pathPrefix || undefined,
          language: input.language || undefined,
        },
      };
    }

    const prompt = this.buildPrompt(input.query, enriched, input.grounded);
    const answer = await this.chat(prompt.system, prompt.user, input.llmModel);

    return {
      answer: answer.trim() || '(sem resposta)',
      evidences: enriched,
      meta: {
        scope: this.toScopeMeta(input.scope),
        topK: input.topK,
        minScore: input.minScore,
        llmModel: input.llmModel,
        contentType: input.contentType,
        strict: input.strict,
        repo: input.scope.type === 'repo' ? input.scope.repos[0] : undefined,
        collection: searchOutput.meta.collection,
        collections: searchOutput.meta.collections,
        totalMatches: searchOutput.results.length,
        contextsUsed: enriched.length,
        elapsedMs: Date.now() - startedAt,
        pathPrefix: input.pathPrefix || undefined,
        language: input.language || undefined,
      },
    };
  }

  private validateInput(rawInput: unknown): ValidatedAskInput {
    if (!rawInput || typeof rawInput !== 'object') {
      throw new ToolInputError('Input inválido: esperado objeto');
    }

    const input = rawInput as AskCodeInput;
    const scope = resolveScope(
      {
        scope: input.scope,
        repo: input.repo,
      },
      process.env,
    );
    const query = this.validateQuery(input.query);
    const topK = this.clampTopK(input.topK);
    const pathPrefix = this.validatePathPrefix(input.pathPrefix);
    const language = this.validateLanguage(input.language);
    const minScore = this.validateMinScore(input.minScore);
    const llmModel = this.validateModel(input.llmModel);
    const grounded = this.validateGrounded(input.grounded);
    const contentType = this.validateContentType(input.contentType);
    const strict = this.validateStrict(input.strict);

    return {
      scope,
      query,
      topK,
      pathPrefix,
      language,
      minScore,
      llmModel,
      grounded,
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

  private validateLanguage(language: unknown): string {
    if (language === undefined || language === null) {
      return '';
    }
    if (typeof language !== 'string') {
      throw new ToolInputError('Campo "language" deve ser string');
    }

    const normalized = language.trim().toLowerCase();
    if (normalized.length > MAX_LANGUAGE_CHARS) {
      throw new ToolInputError(`Campo "language" deve ter no máximo ${MAX_LANGUAGE_CHARS} caracteres`);
    }

    return normalized;
  }

  private validateMinScore(minScore: unknown): number {
    if (minScore === undefined || minScore === null) {
      return DEFAULT_MIN_SCORE;
    }
    if (typeof minScore !== 'number' || Number.isNaN(minScore) || !Number.isFinite(minScore)) {
      throw new ToolInputError('Campo "minScore" deve ser number finito');
    }
    return minScore;
  }

  private validateModel(llmModel: unknown): string {
    if (llmModel === undefined || llmModel === null) {
      return process.env.LLM_MODEL || DEFAULT_LLM_MODEL;
    }
    if (typeof llmModel !== 'string') {
      throw new ToolInputError('Campo "llmModel" deve ser string');
    }
    const normalized = llmModel.trim();
    if (!normalized) {
      throw new ToolInputError('Campo "llmModel" não pode ser vazio');
    }
    return normalized;
  }

  private validateGrounded(grounded: unknown): boolean {
    if (grounded === undefined || grounded === null) {
      return false;
    }
    if (typeof grounded !== 'boolean') {
      throw new ToolInputError('Campo "grounded" deve ser boolean');
    }
    return grounded;
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

  private matchesLanguage(pathValue: string, language: string): boolean {
    if (!language) {
      return true;
    }

    const lowerPath = pathValue.toLowerCase();

    if (language.startsWith('.')) {
      return lowerPath.endsWith(language);
    }

    const mapped = LANGUAGE_EXTENSIONS[language];
    if (!mapped) {
      return lowerPath.endsWith(`.${language}`);
    }

    return mapped.some((ext) => lowerPath.endsWith(ext));
  }

  private async enrichEvidences(
    scope: ResolvedScope,
    evidences: SearchCodeResult[],
  ): Promise<SearchCodeResult[]> {
    const enriched: SearchCodeResult[] = [];
    const perRepoCounter = new Map<string, number>();
    const shouldLimitPerRepo = scope.type !== 'repo';

    for (const evidence of evidences) {
      if (shouldLimitPerRepo) {
        const currentCount = perRepoCounter.get(evidence.repo) ?? 0;
        if (currentCount >= MAX_CONTEXTS_PER_REPO_WIDE_SCOPE) {
          continue;
        }
        perRepoCounter.set(evidence.repo, currentCount + 1);
      }

      const startLine = evidence.startLine ?? 1;
      const endLine = evidence.endLine ?? startLine + 50;

      try {
        const file = await this.openFileTool.execute({
          repo: evidence.repo,
          path: evidence.path,
          startLine,
          endLine,
        });
        const snippet = file.text.trim();

        enriched.push({
          ...evidence,
          startLine: file.startLine,
          endLine: file.endLine,
          snippet: snippet || evidence.snippet,
        });
      } catch {
        enriched.push(evidence);
      }
    }

    return enriched;
  }

  private toScopeInput(scope: ResolvedScope): AskCodeInput['scope'] {
    if (scope.type === 'all') {
      return { type: 'all' };
    }

    if (scope.type === 'repo') {
      return {
        type: 'repo',
        repo: scope.repos[0],
      };
    }

    return {
      type: 'repos',
      repos: [...scope.repos],
    };
  }

  private toScopeMeta(scope: ResolvedScope): AskCodeOutput['meta']['scope'] {
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

  private buildPrompt(
    question: string,
    evidences: SearchCodeResult[],
    grounded: boolean,
  ): { system: string; user: string } {
    const system = [
      'Voce e um assistente especializado em analisar codigo-fonte.',
      'Responda as perguntas do usuario baseando-se APENAS no contexto fornecido.',
      'Se a informacao nao estiver no contexto, diga que nao encontrou essa informacao no codigo indexado.',
      grounded
        ? 'Nao invente exemplos nem APIs. Use somente o que aparece nos trechos. Cite os arquivos relevantes.'
        : 'Seja conciso e direto. Responda em portugues brasileiro.',
    ].join('\n');

    const sections = evidences.map((evidence, index) => {
      const startLine = evidence.startLine ?? '?';
      const endLine = evidence.endLine ?? '?';
      const snippet = evidence.snippet.trim() || '[conteudo nao disponivel]';
      return `### Arquivo ${index + 1}: ${evidence.path} (linhas ${startLine}-${endLine})\n\n\`\`\`\n${snippet}\n\`\`\``;
    });

    const user = [
      '## Contexto do codigo-fonte:',
      '',
      sections.join('\n\n'),
      '',
      '## Pergunta:',
      question,
      '',
      '## Resposta:',
    ].join('\n');

    return { system, user };
  }

  private buildGroundedAnswer(evidences: SearchCodeResult[]): string {
    const header = 'Resposta baseada estritamente nas evidencias abaixo:';
    const items = evidences.map((evidence) => {
      const startLine = evidence.startLine ?? '?';
      const endLine = evidence.endLine ?? '?';
      const snippet = evidence.snippet.trim() || '[conteudo nao disponivel]';
      return [
        `- ${evidence.path} (linhas ${startLine}-${endLine})`,
        '```',
        snippet,
        '```',
      ].join('\n');
    });

    return [header, '', ...items].join('\n');
  }

  private async embedQuestion(query: string): Promise<number[]> {
    const ollamaUrl = process.env.OLLAMA_URL || DEFAULT_OLLAMA_URL;
    const embeddingModel = process.env.EMBEDDING_MODEL || DEFAULT_EMBEDDING_MODEL;

    let response;
    try {
      response = await axios.post<{ embeddings?: number[][] }>(
        `${ollamaUrl.replace(/\/$/, '')}/api/embed`,
        {
          model: embeddingModel,
          input: [query],
        },
        {
          timeout: DEFAULT_TIMEOUT_MS,
        },
      );
    } catch (error) {
      const details = axios.isAxiosError(error)
        ? error.message
        : error instanceof Error
          ? error.message
          : 'erro desconhecido';
      throw new ToolExecutionError(
        'EMBEDDING_FAILED',
        `Falha ao gerar embedding via Ollama (${ollamaUrl} / ${embeddingModel}): ${details}`,
      );
    }

    const embeddings = response.data?.embeddings;
    if (!Array.isArray(embeddings) || embeddings.length === 0 || !Array.isArray(embeddings[0])) {
      throw new ToolExecutionError(
        'EMBEDDING_INVALID',
        'Resposta de embedding inválida do Ollama. Verifique OLLAMA_URL e EMBEDDING_MODEL.',
      );
    }

    return embeddings[0] as number[];
  }

  private async chat(systemPrompt: string, userMessage: string, llmModel: string): Promise<string> {
    const ollamaUrl = process.env.OLLAMA_URL || DEFAULT_OLLAMA_URL;
    let response;
    try {
      response = await axios.post<{ message?: { content?: string } }>(
        `${ollamaUrl.replace(/\/$/, '')}/api/chat`,
        {
          model: llmModel,
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userMessage },
          ],
          stream: false,
        },
        {
          timeout: DEFAULT_TIMEOUT_MS,
        },
      );
    } catch (error) {
      const details = axios.isAxiosError(error)
        ? error.message
        : error instanceof Error
          ? error.message
          : 'erro desconhecido';
      throw new ToolExecutionError(
        'CHAT_FAILED',
        `Falha ao gerar resposta via Ollama (${ollamaUrl} / ${llmModel}): ${details}`,
      );
    }

    return response.data?.message?.content || '';
  }
}
