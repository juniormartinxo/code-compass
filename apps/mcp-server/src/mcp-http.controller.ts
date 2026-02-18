import { Body, Controller, HttpCode, HttpStatus, Post, Res } from '@nestjs/common';
import { McpProtocolHandler } from './mcp-protocol.handler';

@Controller('mcp')
export class McpHttpController {
  constructor(private readonly protocolHandler: McpProtocolHandler) {}

  @Post()
  @HttpCode(HttpStatus.OK)
  async handle(@Body() body: unknown, @Res() response: any): Promise<Response> {
    if (!this.protocolHandler.isMcpRequest(body)) {
      return response.status(HttpStatus.BAD_REQUEST).json({
        jsonrpc: '2.0',
        id: null,
        error: {
          code: -32600,
          message: 'Request inválido para protocolo MCP.',
        },
      });
    }

    const result = await this.protocolHandler.handleMcpRequest(body);
    if (!result) {
      return response.status(HttpStatus.NO_CONTENT).send();
    }

    return response.status(HttpStatus.OK).json(result);
  }
}
