import { Module } from '@nestjs/common';

import { AskCodeTool } from './ask-code.tool';
import { FileService } from './file.service';
import { McpHttpController } from './mcp-http.controller';
import { McpProtocolHandler } from './mcp-protocol.handler';
import { McpStdioServer } from './mcp-stdio.server';
import { OpenFileTool } from './open-file.tool';
import { QdrantService } from './qdrant.service';
import { SearchCodeTool } from './search-code.tool';

@Module({
  controllers: [McpHttpController],
  providers: [
    QdrantService,
    SearchCodeTool,
    FileService,
    OpenFileTool,
    AskCodeTool,
    McpProtocolHandler,
    McpStdioServer,
  ],
})
export class AppModule {}
