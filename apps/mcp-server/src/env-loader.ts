import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function parseEnvLine(line: string): { key: string; value: string } | null {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('#')) {
    return null;
  }

  const withoutExport = trimmed.startsWith('export ')
    ? trimmed.slice('export '.length).trim()
    : trimmed;

  const separatorIndex = withoutExport.indexOf('=');
  if (separatorIndex <= 0) {
    return null;
  }

  const key = withoutExport.slice(0, separatorIndex).trim();
  if (!/^[A-Z_][A-Z0-9_]*$/i.test(key)) {
    return null;
  }

  const rawValue = withoutExport.slice(separatorIndex + 1).trim();

  if (rawValue.startsWith('"') && rawValue.endsWith('"') && rawValue.length >= 2) {
    const value = rawValue.slice(1, -1).replace(/\\n/g, '\n');
    return { key, value };
  }

  if (rawValue.startsWith("'") && rawValue.endsWith("'") && rawValue.length >= 2) {
    return { key, value: rawValue.slice(1, -1) };
  }

  return { key, value: rawValue };
}

function loadEnvFileIntoProcess(envPath: string): void {
  const fileContent = readFileSync(envPath, 'utf-8');
  const lines = fileContent.split(/\r?\n/);

  for (const line of lines) {
    const parsed = parseEnvLine(line);
    if (!parsed) {
      continue;
    }

    if (process.env[parsed.key] !== undefined) {
      continue;
    }

    process.env[parsed.key] = parsed.value;
  }
}

export function loadMcpEnvFiles(cwd: string = process.cwd()): void {
  const candidatePaths = [
    resolve(cwd, '.env.local'),
    resolve(cwd, '.env'),
    resolve(cwd, '..', '..', '.env.local'),
    resolve(cwd, '..', '..', '.env'),
  ];

  const visited = new Set<string>();
  for (const envPath of candidatePaths) {
    if (visited.has(envPath)) {
      continue;
    }
    visited.add(envPath);

    if (!existsSync(envPath)) {
      continue;
    }

    loadEnvFileIntoProcess(envPath);
  }
}
