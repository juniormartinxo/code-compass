import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import { join, resolve, sep } from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, describe, expect, it } from 'vitest';

import { ToolExecutionError } from '../src/errors';
import { FileService, isWithinRoot, sanitizeAndNormalizePath } from '../src/file.service';

function makeLines(total: number): string {
  return Array.from({ length: total }, (_, index) => `line-${index + 1}`).join('\n');
}

describe('FileService path guards', () => {
  it('deve rejeitar path traversal, absolutos, windows drive e null byte', () => {
    expect(() => sanitizeAndNormalizePath('../x')).toThrowError(ToolExecutionError);
    expect(() => sanitizeAndNormalizePath('/etc/passwd')).toThrowError(ToolExecutionError);
    expect(() => sanitizeAndNormalizePath('C:\\Windows\\system32')).toThrowError(
      ToolExecutionError,
    );
    expect(() => sanitizeAndNormalizePath('a/../../b')).toThrowError(ToolExecutionError);
    expect(() => sanitizeAndNormalizePath(`safe\0path`)).toThrowError(ToolExecutionError);
  });

  it('deve aceitar path relativo válido', () => {
    expect(sanitizeAndNormalizePath('apps/mcp-server/src/main.ts')).toBe(
      'apps/mcp-server/src/main.ts',
    );
  });

  it('deve validar containment no root', () => {
    const root = `/tmp/repo`;
    expect(isWithinRoot(root, `/tmp/repo${sep}apps${sep}mcp-server`)).toBe(true);
    expect(isWithinRoot(root, `/tmp/repo-other${sep}apps`)).toBe(false);
  });
});

describe('FileService integration-ish', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    delete process.env.REPO_ROOT;
    await Promise.all(tempRoots.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it('deve abrir range 10-20 com 11 linhas', async () => {
    const repoRoot = mkdtempSync(join(tmpdir(), 'mcp-open-file-'));
    tempRoots.push(repoRoot);

    writeFileSync(join(repoRoot, 'safe.txt'), `${makeLines(300)}\n`, 'utf8');

    process.env.REPO_ROOT = repoRoot;
    const service = new FileService();

    const output = await service.openRange({
      path: 'safe.txt',
      startLine: 10,
      endLine: 20,
    });

    const lines = output.text.trimEnd().split('\n');
    expect(lines).toHaveLength(11);
    expect(lines[0]).toBe('line-10');
    expect(lines[10]).toBe('line-20');
    expect(output.path).toBe('safe.txt');
    expect(output.startLine).toBe(10);
    expect(output.endLine).toBe(20);
  });

  it('deve bloquear traversal ../../etc/passwd', async () => {
    const repoRoot = mkdtempSync(join(tmpdir(), 'mcp-open-file-'));
    tempRoots.push(repoRoot);

    process.env.REPO_ROOT = repoRoot;
    const service = new FileService();

    await expect(service.openRange({ path: '../../etc/passwd' })).rejects.toMatchObject({
      name: 'ToolExecutionError',
      code: 'FORBIDDEN',
    });
  });

  it('deve bloquear symlink escape para fora do root', async () => {
    const repoRoot = mkdtempSync(join(tmpdir(), 'mcp-open-file-'));
    const outsideRoot = mkdtempSync(join(tmpdir(), 'mcp-open-file-outside-'));
    tempRoots.push(repoRoot, outsideRoot);

    const outsideFile = join(outsideRoot, 'outside.txt');
    writeFileSync(outsideFile, 'outside\n', 'utf8');
    symlinkSync(outsideFile, join(repoRoot, 'link-out'));

    process.env.REPO_ROOT = repoRoot;
    const service = new FileService();

    await expect(service.openRange({ path: 'link-out' })).rejects.toMatchObject({
      name: 'ToolExecutionError',
      code: 'FORBIDDEN',
    });
  });

  it('deve detectar binário por byte nulo', async () => {
    const repoRoot = mkdtempSync(join(tmpdir(), 'mcp-open-file-'));
    tempRoots.push(repoRoot);

    const binaryPath = join(repoRoot, 'binary.txt');
    mkdirSync(resolve(repoRoot), { recursive: true });
    writeFileSync(binaryPath, Buffer.from([0x61, 0x00, 0x62]));

    process.env.REPO_ROOT = repoRoot;
    const service = new FileService();

    await expect(service.openRange({ path: 'binary.txt' })).rejects.toMatchObject({
      name: 'ToolExecutionError',
      code: 'UNSUPPORTED_MEDIA',
    });
  });
});
