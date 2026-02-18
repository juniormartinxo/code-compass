import { promises as fs } from 'node:fs';
import { join, resolve, sep } from 'node:path';

import { ToolExecutionError, ToolInputError } from './errors';

const MAX_REPO_CHARS = 200;

type RepoValidationErrorFactory = (message: string) => Error;

function defaultRepoValidationErrorFactory(message: string): Error {
  return new ToolInputError(message);
}

function toToolExecutionError(message: string): Error {
  return new ToolExecutionError('BAD_REQUEST', message);
}

export function validateRepoName(
  repo: unknown,
  onError: RepoValidationErrorFactory = defaultRepoValidationErrorFactory,
): string {
  if (typeof repo !== 'string') {
    throw onError('Campo "repo" deve ser string');
  }

  const normalized = repo.trim();
  if (!normalized) {
    throw onError('Campo "repo" é obrigatório e não pode ser vazio');
  }

  if (normalized.length > MAX_REPO_CHARS) {
    throw onError(`Campo "repo" deve ter no máximo ${MAX_REPO_CHARS} caracteres`);
  }

  if (normalized.includes('\0')) {
    throw onError('Campo "repo" contém sequência inválida');
  }

  if (normalized.includes('/') || normalized.includes('\\')) {
    throw onError('Campo "repo" deve ser apenas o nome do repositório');
  }

  if (normalized.includes('..')) {
    throw onError('Campo "repo" contém sequência inválida');
  }

  return normalized;
}

function isWithinRoot(rootPath: string, candidatePath: string): boolean {
  if (candidatePath === rootPath) {
    return true;
  }
  return candidatePath.startsWith(`${rootPath}${sep}`);
}

async function realpathOrThrow(pathValue: string, message: string): Promise<string> {
  try {
    return await fs.realpath(pathValue);
  } catch (error) {
    const maybeErrno = error as NodeJS.ErrnoException;
    if (maybeErrno?.code === 'ENOENT') {
      throw new ToolExecutionError('NOT_FOUND', message);
    }
    throw error;
  }
}

export async function resolveRepoRoot(
  repo: unknown,
  env: NodeJS.ProcessEnv,
): Promise<{ repoRoot: string; repoName: string }> {
  const repoName = validateRepoName(repo, toToolExecutionError);
  const codebaseRootByEnv = env.CODEBASE_ROOT?.trim();

  if (!codebaseRootByEnv) {
    throw new ToolExecutionError(
      'BAD_REQUEST',
      'CODEBASE_ROOT é obrigatório no modo atual.',
    );
  }

  if (codebaseRootByEnv.includes('\0')) {
    throw new ToolExecutionError('BAD_REQUEST', 'CODEBASE_ROOT inválido.');
  }

  const codebaseRootCandidate = resolve(codebaseRootByEnv);
  const realCodebaseRoot = await realpathOrThrow(codebaseRootCandidate, 'Codebase root not found.');
  const codebaseStat = await fs.stat(realCodebaseRoot);
  if (!codebaseStat.isDirectory()) {
    throw new ToolExecutionError('BAD_REQUEST', 'CODEBASE_ROOT inválido.');
  }

  const repoRootCandidate = join(realCodebaseRoot, repoName);
  const realRepoRoot = await realpathOrThrow(repoRootCandidate, 'Repository not found.');

  if (!isWithinRoot(realCodebaseRoot, realRepoRoot)) {
    throw new ToolExecutionError('FORBIDDEN', 'Repository path escapes codebase root.');
  }

  const repoStat = await fs.stat(realRepoRoot);
  if (!repoStat.isDirectory()) {
    throw new ToolExecutionError('BAD_REQUEST', 'Repository root must be a directory.');
  }

  return {
    repoRoot: realRepoRoot,
    repoName,
  };
}
