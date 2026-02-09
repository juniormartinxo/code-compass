import { Injectable, Logger } from '@nestjs/common';
import * as readline from 'node:readline';

import { ToolExecutionError, ToolInputError } from './errors';
import { OpenFileTool } from './open-file.tool';
import { SearchCodeTool } from './search-code.tool';
import {
  StdioErrorCode,
  StdioToolErrorResponse,
  StdioToolOutput,
  StdioToolRequest,
  StdioToolResponse,
  StdioToolSuccessResponse,
} from './types';

@Injectable()
export class McpStdioServer {
  private readonly logger = new Logger(McpStdioServer.name);
  private rl?: readline.Interface;

  constructor(
    private readonly searchCodeTool: SearchCodeTool,
    private readonly openFileTool: OpenFileTool,
  ) {}

  run(): void {
    if (this.rl) {
      return;
    }

    this.rl = readline.createInterface({
      input: process.stdin,
      crlfDelay: Infinity,
      terminal: false,
    });

    this.rl.on('line', async (line: string) => {
      await this.handleLine(line);
    });

    this.rl.on('close', () => {
      this.logger.log('stdin encerrado');
      this.rl = undefined;
    });
  }

  private async handleLine(line: string): Promise<void> {
    if (!line.trim()) {
      return;
    }

    const request = this.parseRequest(line);
    if (!request) {
      return;
    }

    try {
      const output = await this.dispatchTool(request);
      const response: StdioToolSuccessResponse = {
        id: request.id,
        ok: true,
        output,
      };
      this.writeResponse(response);
    } catch (error) {
      if (error instanceof ToolInputError) {
        this.writeResponse({
          id: request.id,
          ok: false,
          error: {
            code: 'BAD_REQUEST',
            message: error.message,
          },
        });
        return;
      }

      if (error instanceof ToolExecutionError) {
        this.writeResponse({
          id: request.id,
          ok: false,
          error: {
            code: error.code,
            message: error.message,
          },
        });
        return;
      }

      this.logger.error(`Erro interno ao processar request id=${request.id}`);
      this.writeResponse({
        id: request.id,
        ok: false,
        error: {
          code: 'INTERNAL',
          message: 'Erro interno ao executar tool',
        },
      });
    }
  }

  private async dispatchTool(request: StdioToolRequest): Promise<StdioToolOutput> {
    if (request.tool === 'search_code') {
      return this.searchCodeTool.execute(request.input);
    }

    if (request.tool === 'open_file') {
      return this.openFileTool.execute(request.input);
    }

    throw new ToolExecutionError('BAD_REQUEST', `Tool não suportada: ${request.tool}`);
  }

  private parseRequest(line: string): StdioToolRequest | null {
    try {
      const parsed = JSON.parse(line) as Partial<StdioToolRequest>;

      if (!parsed || typeof parsed !== 'object') {
        this.writeProtocolError('BAD_REQUEST', 'Payload NDJSON inválido', 'unknown');
        return null;
      }

      const id = typeof parsed.id === 'string' && parsed.id.trim() ? parsed.id : 'unknown';
      const tool = typeof parsed.tool === 'string' ? parsed.tool : '';

      if (!tool) {
        this.writeProtocolError('BAD_REQUEST', 'Campo "tool" é obrigatório', id);
        return null;
      }

      return {
        id,
        tool,
        input: parsed.input,
      };
    } catch {
      this.writeProtocolError('BAD_REQUEST', 'Linha não é JSON válido', 'unknown');
      return null;
    }
  }

  private writeProtocolError(
    code: StdioErrorCode,
    message: string,
    id: string,
  ): void {
    const response: StdioToolErrorResponse = {
      id,
      ok: false,
      error: {
        code,
        message,
      },
    };
    this.writeResponse(response);
  }

  private writeResponse(response: StdioToolResponse): void {
    process.stdout.write(`${JSON.stringify(response)}\n`);
  }
}
