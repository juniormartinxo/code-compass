import { Injectable } from '@nestjs/common';

import { ToolExecutionError, ToolInputError } from './errors';
import { AskCodeTool } from './ask-code.tool';
import { OpenFileTool } from './open-file.tool';
import { SearchCodeTool } from './search-code.tool';
import { StdioToolOutput, StdioToolRequest } from './types';

export type McpJsonRpcId = string | number | null;

export interface McpJsonRpcRequest {
  jsonrpc: '2.0';
  id?: McpJsonRpcId;
  method: string;
  params?: Record<string, unknown>;
}

export interface McpJsonRpcResponse {
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

@Injectable()
export class McpProtocolHandler {
  constructor(
    private readonly searchCodeTool: SearchCodeTool,
    private readonly openFileTool: OpenFileTool,
    private readonly askCodeTool: AskCodeTool,
  ) {}

  isMcpRequest(parsed: unknown): parsed is McpJsonRpcRequest {
    if (!parsed || typeof parsed !== 'object') {
      return false;
    }
    const request = parsed as McpJsonRpcRequest;
    return request.jsonrpc === '2.0' && typeof request.method === 'string';
  }

  async handleMcpRequest(request: McpJsonRpcRequest): Promise<McpJsonRpcResponse | undefined> {
    const id = request.id ?? null;

    if (request.method === 'initialize') {
      return this.response(id, {
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
    }

    if (request.method === 'initialized') {
      return undefined;
    }

    if (request.method === 'tools/list') {
      return this.response(id, {
        tools: this.describeTools(),
      });
    }

    if (request.method === 'tools/call') {
      const params = (request.params ?? {}) as Record<string, unknown>;
      const name = typeof params.name === 'string' ? params.name : '';
      const args = (params.arguments ?? {}) as Record<string, unknown>;

      if (!name) {
        return this.error(id, -32602, 'Campo "name" é obrigatório em tools/call');
      }

      try {
        const output = await this.dispatchTool({
          id: 'mcp',
          tool: name,
          input: args,
        });

        return this.response(id, {
          content: [
            {
              type: 'text',
              text: JSON.stringify(output),
            },
          ],
        });
      } catch (error) {
        if (error instanceof ToolInputError || error instanceof ToolExecutionError) {
          return this.response(id, {
            isError: true,
            content: [
              {
                type: 'text',
                text: error.message,
              },
            ],
          });
        }

        return this.response(id, {
          isError: true,
          content: [
            {
              type: 'text',
              text: 'Erro interno ao executar tool',
            },
          ],
        });
      }
    }

    if (id === null) {
      return undefined;
    }

    return this.error(id, -32601, `Método não suportado: ${request.method}`);
  }

  async dispatchTool(request: StdioToolRequest): Promise<StdioToolOutput> {
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

  private describeTools(): McpToolDescriptor[] {
    return [
      {
        name: 'search_code',
        description: 'Busca semântica por trechos de código com evidência (path + linhas).',
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          required: ['query', 'scope'],
          properties: {
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
            contentType: {
              type: 'string',
              enum: ['code', 'docs', 'all'],
              default: 'all',
            },
            strict: {
              type: 'boolean',
              default: false,
              description:
                'When true, returns an error if any collection is unavailable instead of partial results.',
            },
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
          required: ['query', 'scope'],
          properties: {
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
            grounded: { type: 'boolean' },
            contentType: {
              type: 'string',
              enum: ['code', 'docs', 'all'],
              default: 'all',
            },
            strict: {
              type: 'boolean',
              default: false,
              description:
                'When true, returns an error if any collection is unavailable instead of partial results.',
            },
          },
        },
      },
    ];
  }

  private response(id: McpJsonRpcId, result: Record<string, unknown>): McpJsonRpcResponse {
    return {
      jsonrpc: '2.0',
      id,
      result,
    };
  }

  private error(id: McpJsonRpcId, code: number, message: string): McpJsonRpcResponse {
    return {
      jsonrpc: '2.0',
      id,
      error: {
        code,
        message,
      },
    };
  }
}
