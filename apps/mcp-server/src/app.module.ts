import { Module } from '@nestjs/common';

import { FileService } from './file.service';
import { McpStdioServer } from './mcp-stdio.server';
import { OpenFileTool } from './open-file.tool';
import { QdrantService } from './qdrant.service';
import { SearchCodeTool } from './search-code.tool';

@Module({
  providers: [QdrantService, SearchCodeTool, FileService, OpenFileTool, McpStdioServer],
})
export class AppModule {}
