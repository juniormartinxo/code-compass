import 'reflect-metadata';

import { NestFactory } from '@nestjs/core';

import { AppModule } from './app.module';
import { loadMcpEnvFiles } from './env-loader';
import { McpStdioServer } from './mcp-stdio.server';
import { resolveHttpHost, resolveHttpPort, resolveTransport } from './transport';

async function bootstrap(): Promise<void> {
  loadMcpEnvFiles();

  const transport = resolveTransport({
    argv: process.argv.slice(2),
    env: process.env,
  });

  if (transport === 'stdio') {
    const app = await NestFactory.createApplicationContext(AppModule, {
      logger: ['error', 'warn'],
    });

    const stdioServer = app.get(McpStdioServer);
    stdioServer.run();
    return;
  }

  const app = await NestFactory.create(AppModule, {
    logger: ['error', 'warn'],
  });

  const host = resolveHttpHost(process.env);
  const port = resolveHttpPort(process.env);

  await app.listen(port, host);
  process.stderr.write(`[mcp] HTTP escutando em http://${host}:${port}/mcp\n`);
}

bootstrap().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : 'erro desconhecido';
  process.stderr.write(`[bootstrap] falha: ${message}\n`);
  process.exitCode = 1;
});
