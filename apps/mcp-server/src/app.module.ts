import { Module } from '@nestjs/common';

import { FileService } from './file.service';
import { McpStdioServer } from './mcp-stdio.server';
import { OpenFileTool } from './open-file.tool';
import { QdrantService } from './qdrant.service';
import { AskCodeTool } from './ask-code.tool';
import { SearchCodeTool } from './search-code.tool';

@Module({
  providers: [
    QdrantService,
    SearchCodeTool,
    FileService,
    OpenFileTool,
    AskCodeTool,
    McpStdioServer,
  ],
})
export class AppModule {}
