import { describe, expect, it } from 'vitest';

import { resolveHttpHost, resolveHttpPort, resolveTransport } from '../src/transport';

describe('transport resolver', () => {
  it('deve priorizar flag --transport http', () => {
    expect(resolveTransport({ argv: ['--transport', 'http'], env: {} })).toBe('http');
  });

  it('deve aceitar MCP_SERVER_MODE=http sem flag', () => {
    expect(resolveTransport({ argv: [], env: { MCP_SERVER_MODE: 'http' } })).toBe('http');
  });

  it('deve manter stdio como default', () => {
    expect(resolveTransport({ argv: [], env: {} })).toBe('stdio');
  });

  it('deve resolver porta e host HTTP com defaults seguros', () => {
    expect(resolveHttpPort({})).toBe(3001);
    expect(resolveHttpHost({})).toBe('0.0.0.0');
    expect(resolveHttpPort({ MCP_HTTP_PORT: '4010' })).toBe(4010);
    expect(resolveHttpHost({ MCP_HTTP_HOST: '127.0.0.1' })).toBe('127.0.0.1');
  });
});
