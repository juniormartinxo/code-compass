import { Injectable } from '@nestjs/common';
import { createReadStream, promises as fs } from 'node:fs';
import { isAbsolute, posix, resolve, sep } from 'node:path';
import * as readline from 'node:readline';

import { ToolExecutionError } from './errors';
import { OpenFileInput, OpenFileOutput } from './types';
import { resolveRepoRoot } from './repo-root';

const DEFAULT_START_LINE = 1;
const DEFAULT_LINE_WINDOW = 50;
const MAX_LINE_RANGE = 200;
const DEFAULT_MAX_BYTES = 200_000;
const MAX_ALLOWED_BYTES = 1_000_000;

function hasForbiddenParentSegment(normalizedPath: string): boolean {
  if (normalizedPath === '..') {
    return true;
  }
  return (
    normalizedPath.startsWith('../') ||
    normalizedPath.includes('/../') ||
    normalizedPath.includes('..')
  );
}

function isWindowsAbsolutePath(rawPath: string): boolean {
  return /^[a-zA-Z]:[\\/]/.test(rawPath) || /^\\\\/.test(rawPath);
}

export function sanitizeAndNormalizePath(inputPath: unknown): string {
  if (typeof inputPath !== 'string') {
    throw new ToolExecutionError('BAD_REQUEST', 'Field "path" must be a string.');
  }

  const trimmedPath = inputPath.trim();
  if (!trimmedPath) {
    throw new ToolExecutionError('BAD_REQUEST', 'Field "path" is required.');
  }

  if (trimmedPath.includes('\0')) {
    throw new ToolExecutionError('BAD_REQUEST', 'Path contains invalid sequence.');
  }

  if (isAbsolute(trimmedPath) || isWindowsAbsolutePath(trimmedPath)) {
    throw new ToolExecutionError('BAD_REQUEST', 'Absolute paths are not allowed.');
  }

  const normalized = posix.normalize(trimmedPath.replace(/\\/g, '/'));
  if (!normalized || normalized === '.' || normalized.startsWith('/')) {
    throw new ToolExecutionError('BAD_REQUEST', 'Path is invalid.');
  }

  if (hasForbiddenParentSegment(normalized)) {
    throw new ToolExecutionError('FORBIDDEN', 'Path escapes repository root.');
  }

  return normalized;
}

export function isWithinRoot(rootPath: string, candidatePath: string): boolean {
  if (candidatePath === rootPath) {
    return true;
  }
  return candidatePath.startsWith(`${rootPath}${sep}`);
}

function clampPositiveInteger(value: unknown, fallback: number): number {
  if (value === undefined || value === null) {
    return fallback;
  }

  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ToolExecutionError('BAD_REQUEST', 'Line and byte limits must be numbers.');
  }

  const integer = Math.trunc(value);
  if (integer < 1) {
    throw new ToolExecutionError('BAD_REQUEST', 'Line and byte limits must be >= 1.');
  }

  return integer;
}

function resolveRange(input: OpenFileInput): {
  startLine: number;
  endLine: number;
  maxBytes: number;
} {
  const startLine = clampPositiveInteger(input.startLine, DEFAULT_START_LINE);
  const defaultEndLine = startLine + DEFAULT_LINE_WINDOW;
  const requestedEndLine = clampPositiveInteger(input.endLine, defaultEndLine);

  if (requestedEndLine < startLine) {
    throw new ToolExecutionError('BAD_REQUEST', 'endLine must be >= startLine.');
  }

  const cappedEndLine = Math.min(requestedEndLine, startLine + MAX_LINE_RANGE - 1);
  const maxBytes = Math.min(
    clampPositiveInteger(input.maxBytes, DEFAULT_MAX_BYTES),
    MAX_ALLOWED_BYTES,
  );

  return {
    startLine,
    endLine: cappedEndLine,
    maxBytes,
  };
}

@Injectable()
export class FileService {
  async openRange(rawInput: unknown): Promise<OpenFileOutput> {
    if (!rawInput || typeof rawInput !== 'object') {
      throw new ToolExecutionError('BAD_REQUEST', 'Input must be an object.');
    }

    const input = rawInput as OpenFileInput;
    const { repoRoot: repoRootReal } = await resolveRepoRoot(input.repo, process.env);
    const normalizedPath = sanitizeAndNormalizePath(input.path);
    const { startLine, endLine, maxBytes } = resolveRange(input);

    const candidateResolved = resolve(repoRootReal, normalizedPath);
    if (!isWithinRoot(repoRootReal, candidateResolved)) {
      throw new ToolExecutionError('FORBIDDEN', 'Path escapes repository root.');
    }

    let realPath: string;
    try {
      realPath = await fs.realpath(candidateResolved);
    } catch (error) {
      const maybeErrno = error as NodeJS.ErrnoException;
      if (maybeErrno?.code === 'ENOENT') {
        throw new ToolExecutionError('NOT_FOUND', 'File not found.');
      }
      throw error;
    }

    if (!isWithinRoot(repoRootReal, realPath)) {
      throw new ToolExecutionError('FORBIDDEN', 'Path escapes repository root.');
    }

    const stat = await fs.stat(realPath);
    if (!stat.isFile()) {
      throw new ToolExecutionError('BAD_REQUEST', 'Path must point to a file.');
    }

    await this.ensureTextFile(realPath);

    return this.readRange({
      realPath,
      normalizedPath,
      startLine,
      endLine,
      maxBytes,
    });
  }

  private async ensureTextFile(realPath: string): Promise<void> {
    const fileHandle = await fs.open(realPath, 'r');
    try {
      const probe = Buffer.alloc(8192);
      const { bytesRead } = await fileHandle.read(probe, 0, probe.length, 0);
      const sample = probe.subarray(0, bytesRead);

      if (sample.includes(0)) {
        throw new ToolExecutionError('UNSUPPORTED_MEDIA', 'Binary file not supported.');
      }

      try {
        new TextDecoder('utf-8', { fatal: true }).decode(sample);
      } catch {
        throw new ToolExecutionError('UNSUPPORTED_MEDIA', 'Binary file not supported.');
      }
    } finally {
      await fileHandle.close();
    }
  }

  private async readRange(args: {
    realPath: string;
    normalizedPath: string;
    startLine: number;
    endLine: number;
    maxBytes: number;
  }): Promise<OpenFileOutput> {
    const stream = createReadStream(args.realPath, {
      encoding: 'utf8',
    });
    const rl = readline.createInterface({
      input: stream,
      crlfDelay: Infinity,
      terminal: false,
    });

    const lines: string[] = [];
    let truncated = false;
    let byteCount = 0;
    let totalLines = 0;
    let reachedFileEnd = true;

    try {
      for await (const line of rl) {
        totalLines += 1;

        if (line.includes('\u0000')) {
          throw new ToolExecutionError('UNSUPPORTED_MEDIA', 'Binary file not supported.');
        }

        if (totalLines < args.startLine) {
          continue;
        }

        if (totalLines > args.endLine) {
          reachedFileEnd = false;
          break;
        }

        const lineWithTerminator = `${line}\n`;
        const lineBytes = Buffer.byteLength(lineWithTerminator, 'utf8');

        if (byteCount + lineBytes > args.maxBytes) {
          const remaining = args.maxBytes - byteCount;
          if (remaining > 0) {
            const slice = Buffer.from(lineWithTerminator, 'utf8').slice(0, remaining);
            lines.push(slice.toString('utf8'));
            byteCount += slice.length;
          }
          truncated = true;
          reachedFileEnd = false;
          break;
        }

        lines.push(lineWithTerminator);
        byteCount += lineBytes;
      }

      return {
        path: args.normalizedPath,
        startLine: args.startLine,
        endLine: args.endLine,
        totalLines: reachedFileEnd ? totalLines : null,
        text: lines.join(''),
        truncated,
      };
    } catch (error) {
      if (error instanceof ToolExecutionError) {
        throw error;
      }
      const message = error instanceof Error ? error.message : '';
      if (message.includes('invalid') && message.toLowerCase().includes('utf-8')) {
        throw new ToolExecutionError('UNSUPPORTED_MEDIA', 'Binary file not supported.');
      }
      throw error;
    } finally {
      rl.close();
      stream.destroy();
    }
  }
}
