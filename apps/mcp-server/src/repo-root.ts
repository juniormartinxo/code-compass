import { existsSync, promises as fs, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve, sep } from 'node:path';

import { ToolExecutionError, ToolInputError } from './errors';

const MAX_PARENT_TRAVERSAL = 8;
const MAX_REPO_CHARS = 200;

type RepoValidationErrorFactory = (message: string) => Error;

function hasGitDir(dirPath: string): boolean {
  const gitPath = resolve(dirPath, '.git');
  if (!existsSync(gitPath)) {
    return false;
  }

  try {
    return statSync(gitPath).isDirectory();
  } catch {
    return false;
  }
}

function hasPnpmWorkspace(dirPath: string): boolean {
  return existsSync(resolve(dirPath, 'pnpm-workspace.yaml'));
}

function hasPackageJsonWorkspaces(dirPath: string): boolean {
  const packageJsonPath = resolve(dirPath, 'package.json');
  if (!existsSync(packageJsonPath)) {
    return false;
  }

  try {
    const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf-8')) as Record<
      string,
      unknown
    >;
    return packageJson.workspaces !== undefined;
  } catch {
    return false;
  }
}

function findRepoRootFrom(startDir: string): string | null {
  let current = resolve(startDir);

  for (let depth = 0; depth <= MAX_PARENT_TRAVERSAL; depth += 1) {
    if (
      hasPnpmWorkspace(current) ||
      hasGitDir(current) ||
      hasPackageJsonWorkspaces(current)
    ) {
      return current;
    }

    const parent = dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }

  return null;
}

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

export function resolveSingleRepoRoot(
  env: NodeJS.ProcessEnv,
  startDir: string = __dirname,
): string {
  const byEnv = env.REPO_ROOT?.trim();
  if (byEnv) {
    return resolve(byEnv);
  }

  const inferred = findRepoRootFrom(startDir) ?? findRepoRootFrom(process.cwd());
  if (!inferred) {
    throw new Error('REPO_ROOT not set and could not be inferred.');
  }

  return inferred;
}

export async function resolveRepoRoot(
  repo: unknown,
  env: NodeJS.ProcessEnv,
  startDir: string = __dirname,
): Promise<{ repoRoot: string; repoName: string }> {
  const repoName = validateRepoName(repo, toToolExecutionError);
  const codebaseRootByEnv = env.CODEBASE_ROOT?.trim();

  if (!codebaseRootByEnv) {
    const singleRepoRoot = resolveSingleRepoRoot(env, startDir);
    const realSingleRepoRoot = await realpathOrThrow(singleRepoRoot, 'Repository root not found.');
    return {
      repoRoot: realSingleRepoRoot,
      repoName,
    };
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
