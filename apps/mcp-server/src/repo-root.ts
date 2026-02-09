import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const MAX_PARENT_TRAVERSAL = 8;

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

export function resolveRepoRoot(
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
