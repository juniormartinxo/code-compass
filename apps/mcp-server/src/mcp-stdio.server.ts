import { Injectable, Logger } from '@nestjs/common';

import { ToolExecutionError, ToolInputError } from './errors';
import { AskCodeTool } from './ask-code.tool';
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
  private running = false;
  private framing?: 'lsp' | 'ndjson';
  private buffer: Buffer = Buffer.alloc(0);
  private processing: Promise<void> = Promise.resolve();

  constructor(
    private readonly searchCodeTool: SearchCodeTool,
    private readonly openFileTool: OpenFileTool,
    private readonly askCodeTool: AskCodeTool,
  ) {}

  run(): void {
    if (this.running) {
      return;
    }

    this.running = true;
    process.stdin.on('data', (chunk: Buffer) => {
      this.handleChunk(chunk);
    });

    process.stdin.on('close', () => {
      process.stderr.write('[mcp] stdin encerrado\n');
      this.running = false;
    });
  }

  async handleLine(line: string): Promise<void> {
    const trimmed = line.trim();
    if (!trimmed) {
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed) as unknown;
    } catch {
      this.writeProtocolError('BAD_REQUEST', 'Linha não é JSON válido', 'unknown');
      return;
    }

    await this.handleParsed(parsed);
  }

  private handleChunk(chunk: Buffer): void {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    this.processing = this.processing
      .then(() => this.processBuffer())
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        this.logger.error(`Falha ao processar STDIO: ${message}`);
      });
  }

  private async processBuffer(): Promise<void> {
    if (!this.framing) {
      this.framing = this.detectFraming();
      if (!this.framing) {
        return;
      }
    }

    if (this.framing === 'lsp') {
      await this.processLspBuffer();
      return;
    }

    await this.processNdjsonBuffer();
  }

  private detectFraming(): 'lsp' | 'ndjson' | undefined {
    const headerEnd = this.buffer.indexOf('\r\n\r\n');
    if (headerEnd !== -1) {
      const headerText = this.buffer.slice(0, headerEnd).toString('utf8');
      if (/^content-length:/im.test(headerText)) {
        return 'lsp';
      }
    }

    const preview = this.buffer.toString('utf8', 0, Math.min(this.buffer.length, 64));
    const trimmed = preview.replace(/^\\s+/, '');
    if (/^content-length:/i.test(trimmed)) {
      return 'lsp';
    }

    if (trimmed.startsWith('{')) {
      return 'ndjson';
    }

    return undefined;
  }

  private async processLspBuffer(): Promise<void> {
    while (true) {
      const headerEnd = this.buffer.indexOf('\r\n\r\n');
      if (headerEnd === -1) {
        return;
      }

      const headerText = this.buffer.slice(0, headerEnd).toString('utf8');
      const match = headerText.match(/content-length:\\s*(\\d+)/i);
      if (!match) {
        this.buffer = this.buffer.slice(headerEnd + 4);
        this.writeMcpError(null, -32600, 'Cabeçalho inválido (Content-Length ausente).');
        continue;
      }

      const contentLength = Number(match[1]);
      const bodyStart = headerEnd + 4;
      const bodyEnd = bodyStart + contentLength;
      if (this.buffer.length < bodyEnd) {
        return;
      }

      const body = this.buffer.slice(bodyStart, bodyEnd).toString('utf8');
      this.buffer = this.buffer.slice(bodyEnd);

      await this.handleJsonMessage(body);
    }
  }

  private async processNdjsonBuffer(): Promise<void> {
    const data = this.buffer.toString('utf8');
    const lines = data.split('\n');
    const hasTrailingNewline = data.endsWith('\n');
    const remainder = hasTrailingNewline ? '' : (lines.pop() ?? '');
    this.buffer = Buffer.from(remainder, 'utf8');

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }

      let parsed: unknown;
      try {
        parsed = JSON.parse(trimmed) as unknown;
      } catch {
        this.writeProtocolError('BAD_REQUEST', 'Linha não é JSON válido', 'unknown');
        continue;
      }

      await this.handleParsed(parsed);
    }
  }

  private async handleJsonMessage(body: string): Promise<void> {
    let parsed: unknown;
    try {
      parsed = JSON.parse(body) as unknown;
    } catch {
      this.writeMcpError(null, -32700, 'Linha não é JSON válido');
      return;
    }

    await this.handleParsed(parsed);
  }

  private async handleParsed(parsed: unknown): Promise<void> {
    if (this.isMcpRequest(parsed)) {
      await this.handleMcpRequest(parsed);
      return;
    }

    if (this.framing === 'lsp') {
      this.writeMcpError(null, -32600, 'Request inválido para protocolo MCP.');
      return;
    }

    const request = this.parseLegacyRequest(parsed);
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

    if (request.tool === 'ask_code') {
      return this.askCodeTool.execute(request.input);
    }

    throw new ToolExecutionError('BAD_REQUEST', `Tool não suportada: ${request.tool}`);
  }

  private parseLegacyRequest(parsed: unknown): StdioToolRequest | null {
    if (!parsed || typeof parsed !== 'object') {
      this.writeProtocolError('BAD_REQUEST', 'Payload NDJSON inválido', 'unknown');
      return null;
    }

    const request = parsed as Partial<StdioToolRequest>;
    const id = typeof request.id === 'string' && request.id.trim() ? request.id : 'unknown';
    const tool = typeof request.tool === 'string' ? request.tool : '';

    if (!tool) {
      this.writeProtocolError('BAD_REQUEST', 'Campo "tool" é obrigatório', id);
      return null;
    }

    return {
      id,
      tool,
      input: request.input,
    };
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
    this.writeOutput(JSON.stringify(response));
  }

  private isMcpRequest(parsed: unknown): parsed is McpJsonRpcRequest {
    if (!parsed || typeof parsed !== 'object') {
      return false;
    }
    const request = parsed as McpJsonRpcRequest;
    return request.jsonrpc === '2.0' && typeof request.method === 'string';
  }

  private async handleMcpRequest(request: McpJsonRpcRequest): Promise<void> {
    const id = request.id ?? null;

    if (request.method === 'initialize') {
      this.writeMcpResponse(id, {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {
            listChanged: true,
          },
        },
        serverInfo: {
          name: 'code-compass',
          version: '0.1.0',
        },
      });
      return;
    }

    if (request.method === 'initialized') {
      return;
    }

    if (request.method === 'tools/list') {
      this.writeMcpResponse(id, {
        tools: this.describeTools(),
      });
      return;
    }

    if (request.method === 'tools/call') {
      const params = (request.params ?? {}) as Record<string, unknown>;
      const name = typeof params.name === 'string' ? params.name : '';
      const args = (params.arguments ?? {}) as Record<string, unknown>;

      if (!name) {
        this.writeMcpError(id, -32602, 'Campo "name" é obrigatório em tools/call');
        return;
      }

      try {
        const output = await this.dispatchTool({
          id: 'mcp',
          tool: name,
          input: args,
        });

        this.writeMcpResponse(id, {
          content: [
            {
              type: 'text',
              text: JSON.stringify(output),
            },
          ],
        });
      } catch (error) {
        if (error instanceof ToolInputError) {
          this.writeMcpResponse(id, {
            isError: true,
            content: [
              {
                type: 'text',
                text: error.message,
              },
            ],
          });
          return;
        }

        if (error instanceof ToolExecutionError) {
          this.writeMcpResponse(id, {
            isError: true,
            content: [
              {
                type: 'text',
                text: error.message,
              },
            ],
          });
          return;
        }

        this.writeMcpResponse(id, {
          isError: true,
          content: [
            {
              type: 'text',
              text: 'Erro interno ao executar tool',
            },
          ],
        });
      }
      return;
    }

    if (id === null) {
      return;
    }

    this.writeMcpError(id, -32601, `Método não suportado: ${request.method}`);
  }

  private describeTools(): McpToolDescriptor[] {
    return [
      {
        name: 'search_code',
        description: 'Busca semântica por trechos de código com evidência (path + linhas).',
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          required: ['query'],
          anyOf: [{ required: ['repo'] }, { required: ['scope'] }],
          properties: {
            repo: { type: 'string' },
            scope: {
              oneOf: [
                {
                  type: 'object',
                  additionalProperties: false,
                  required: ['type', 'repo'],
                  properties: {
                    type: { const: 'repo' },
                    repo: { type: 'string' },
                  },
                },
                {
                  type: 'object',
                  additionalProperties: false,
                  required: ['type', 'repos'],
                  properties: {
                    type: { const: 'repos' },
                    repos: {
                      type: 'array',
                      items: { type: 'string' },
                    },
                  },
                },
                {
                  type: 'object',
                  additionalProperties: false,
                  required: ['type'],
                  properties: {
                    type: { const: 'all' },
                  },
                },
              ],
            },
            query: { type: 'string' },
            topK: { type: 'number' },
            pathPrefix: { type: 'string' },
            vector: { type: 'array', items: { type: 'number' } },
          },
        },
      },
      {
        name: 'open_file',
        description: 'Abre trecho de arquivo local com allowlist e limites de tamanho.',
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          required: ['repo', 'path'],
          properties: {
            repo: { type: 'string' },
            path: { type: 'string' },
            startLine: { type: 'number' },
            endLine: { type: 'number' },
            maxBytes: { type: 'number' },
          },
        },
      },
      {
        name: 'ask_code',
        description: 'Executa RAG completo (embed + busca + contexto + LLM) com política centralizada.',
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          required: ['query'],
          anyOf: [{ required: ['repo'] }, { required: ['scope'] }],
          properties: {
            repo: { type: 'string' },
            scope: {
              oneOf: [
                {
                  type: 'object',
                  additionalProperties: false,
                  required: ['type', 'repo'],
                  properties: {
                    type: { const: 'repo' },
                    repo: { type: 'string' },
                  },
                },
                {
                  type: 'object',
                  additionalProperties: false,
                  required: ['type', 'repos'],
                  properties: {
                    type: { const: 'repos' },
                    repos: {
                      type: 'array',
                      items: { type: 'string' },
                    },
                  },
                },
                {
                  type: 'object',
                  additionalProperties: false,
                  required: ['type'],
                  properties: {
                    type: { const: 'all' },
                  },
                },
              ],
            },
            query: { type: 'string' },
            topK: { type: 'number' },
            pathPrefix: { type: 'string' },
            language: { type: 'string' },
            minScore: { type: 'number' },
            llmModel: { type: 'string' },
          },
        },
      },
    ];
  }

  private writeMcpResponse(id: McpJsonRpcId, result: Record<string, unknown>): void {
    const response: McpJsonRpcResponse = {
      jsonrpc: '2.0',
      id,
      result,
    };
    this.writeOutput(JSON.stringify(response));
  }

  private writeMcpError(id: McpJsonRpcId, code: number, message: string): void {
    const response: McpJsonRpcResponse = {
      jsonrpc: '2.0',
      id,
      error: {
        code,
        message,
      },
    };
    this.writeOutput(JSON.stringify(response));
  }

  private writeOutput(payload: string): void {
    if (this.framing === 'lsp') {
      const byteLength = Buffer.byteLength(payload, 'utf8');
      process.stdout.write(`Content-Length: ${byteLength}\r\n\r\n${payload}`);
      return;
    }

    process.stdout.write(`${payload}\n`);
  }
}

type McpJsonRpcId = string | number | null;

interface McpJsonRpcRequest {
  jsonrpc: '2.0';
  id?: McpJsonRpcId;
  method: string;
  params?: Record<string, unknown>;
}

interface McpJsonRpcResponse {
  jsonrpc: '2.0';
  id: McpJsonRpcId;
  result?: Record<string, unknown>;
  error?: {
    code: number;
    message: string;
  };
}

interface McpToolDescriptor {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}
