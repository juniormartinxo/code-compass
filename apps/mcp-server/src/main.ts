import 'reflect-metadata';

import { NestFactory } from '@nestjs/core';

import { AppModule } from './app.module';
import { loadMcpEnvFiles } from './env-loader';
import { McpStdioServer } from './mcp-stdio.server';

function resolveTransport(argv: string[]): 'stdio' | 'http' {
  const transportIndex = argv.findIndex((arg) => arg === '--transport');
  if (transportIndex >= 0 && argv[transportIndex + 1] === 'http') {
    return 'http';
  }
  return 'stdio';
}

async function bootstrap(): Promise<void> {
  loadMcpEnvFiles();

  const transport = resolveTransport(process.argv.slice(2));

  const app = await NestFactory.createApplicationContext(AppModule, {
    logger: ['error', 'warn'],
  });

  if (transport === 'stdio') {
    const stdioServer = app.get(McpStdioServer);
    stdioServer.run();
    return;
  }

  process.stderr.write('Transport HTTP selecionado; encerrando sem iniciar servidor HTTP.\n');
  await app.close();
}

bootstrap().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : 'erro desconhecido';
  process.stderr.write(`[bootstrap] falha: ${message}\n`);
  process.exitCode = 1;
});
