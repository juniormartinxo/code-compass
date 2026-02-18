export type McpTransport = 'stdio' | 'http';

interface ResolveTransportInput {
  argv: string[];
  env: NodeJS.ProcessEnv;
}

export function resolveTransport(input: ResolveTransportInput): McpTransport {
  const transportIndex = input.argv.findIndex((arg) => arg === '--transport');
  if (transportIndex >= 0) {
    return input.argv[transportIndex + 1] === 'http' ? 'http' : 'stdio';
  }

  if (input.env.MCP_SERVER_MODE === 'http') {
    return 'http';
  }

  return 'stdio';
}

export function resolveHttpPort(env: NodeJS.ProcessEnv): number {
  const raw = env.MCP_HTTP_PORT ?? env.PORT;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 3001;
  }
  return parsed;
}

export function resolveHttpHost(env: NodeJS.ProcessEnv): string {
  return env.MCP_HTTP_HOST || '0.0.0.0';
}
