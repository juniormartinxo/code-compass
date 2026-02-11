import { ToolExecutionError, ToolInputError } from './errors';
import { validateRepoName } from './repo-root';
import { ResolvedScope, Scope } from './types';

const MAX_SCOPE_REPOS = 10;

type ResolveScopeInput = {
  scope?: unknown;
  repo?: unknown;
};

function normalizeRepos(repos: unknown): string[] {
  if (!Array.isArray(repos)) {
    throw new ToolInputError('Campo "scope.repos" deve ser array de strings');
  }
  if (repos.length === 0) {
    throw new ToolInputError('Campo "scope.repos" não pode ser vazio');
  }

  const deduped = Array.from(new Set(repos.map((repo) => validateRepoName(repo))));
  if (deduped.length > MAX_SCOPE_REPOS) {
    throw new ToolInputError(`Campo "scope.repos" suporta no máximo ${MAX_SCOPE_REPOS} repos`);
  }

  return deduped;
}

function resolveFromScope(scope: Scope, env: NodeJS.ProcessEnv): ResolvedScope {
  if (scope.type === 'repo') {
    const repo = validateRepoName(scope.repo);
    return {
      type: 'repo',
      repos: [repo],
    };
  }

  if (scope.type === 'repos') {
    const repos = normalizeRepos(scope.repos);
    return {
      type: 'repos',
      repos,
    };
  }

  if (env.ALLOW_GLOBAL_SCOPE !== 'true') {
    throw new ToolExecutionError('FORBIDDEN', 'Global scope não está habilitado.');
  }

  return {
    type: 'all',
    repos: [],
  };
}

function parseScope(rawScope: unknown): Scope {
  if (!rawScope || typeof rawScope !== 'object') {
    throw new ToolInputError('Campo "scope" deve ser objeto');
  }

  const scope = rawScope as Record<string, unknown>;
  const type = scope.type;
  if (type !== 'repo' && type !== 'repos' && type !== 'all') {
    throw new ToolInputError('Campo "scope.type" deve ser "repo", "repos" ou "all"');
  }

  if (type === 'repo') {
    return {
      type,
      repo: scope.repo as string,
    };
  }

  if (type === 'repos') {
    return {
      type,
      repos: scope.repos as string[],
    };
  }

  return {
    type,
  };
}

export function resolveScope(input: ResolveScopeInput, env: NodeJS.ProcessEnv): ResolvedScope {
  if (input.scope !== undefined && input.scope !== null) {
    const parsed = parseScope(input.scope);
    return resolveFromScope(parsed, env);
  }

  const repo = validateRepoName(input.repo);
  return {
    type: 'repo',
    repos: [repo],
  };
}

