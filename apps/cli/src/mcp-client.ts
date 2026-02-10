import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";

import type { OpenFileResponse, SearchCodeResponse } from "./types.js";

export type McpClientOptions = {
  command: string;
  args: string[];
  env?: NodeJS.ProcessEnv;
  debug?: boolean;
};

type PendingRequest = {
  resolve: (value: any) => void;
  reject: (error: Error) => void;
  timeout: NodeJS.Timeout;
};

export class McpClient extends EventEmitter {
  private child: ReturnType<typeof spawn> | null = null;
  private buffer = "";
  private pending = new Map<string, PendingRequest>();
  private debug: boolean;

  constructor(private options: McpClientOptions) {
    super();
    this.debug = Boolean(options.debug);
  }

  start(): void {
    if (this.child) return;
    this.child = spawn(this.options.command, this.options.args, {
      env: this.options.env,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const child = this.child;
    if (!child.stdout || !child.stderr) {
      throw new Error("Falha ao inicializar pipes do MCP server");
    }

    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => this.onStdout(chunk));
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk: string) => {
      if (this.debug) {
        this.emit("debug", chunk.trim());
      }
    });

    child.on("exit", (code) => {
      this.emit("exit", code ?? 0);
      this.failAllPending(new Error("MCP server encerrado"));
      this.child = null;
    });

    child.on("error", (error) => {
      this.emit("error", error);
      this.failAllPending(error instanceof Error ? error : new Error("Erro no MCP"));
    });
  }

  isRunning(): boolean {
    return Boolean(this.child);
  }

  async request<TOutput>(tool: string, input: Record<string, unknown>, timeoutMs = 15000): Promise<TOutput> {
    if (!this.child || !this.child.stdin) {
      throw new Error("MCP server nao iniciado");
    }

    const id = `req-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const payload = JSON.stringify({ id, tool, input });

    const result = new Promise<TOutput>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Timeout aguardando resposta do MCP (${tool})`));
      }, timeoutMs);

      this.pending.set(id, { resolve, reject, timeout });
    });

    this.child.stdin.write(`${payload}\n`);
    return result;
  }

  async searchCode(input: Record<string, unknown>, timeoutMs?: number): Promise<SearchCodeResponse> {
    return this.request<SearchCodeResponse>("search_code", input, timeoutMs);
  }

  async openFile(input: Record<string, unknown>, timeoutMs?: number): Promise<OpenFileResponse> {
    return this.request<OpenFileResponse>("open_file", input, timeoutMs);
  }

  close(): void {
    if (!this.child) return;
    this.child.kill();
    this.child = null;
  }

  private onStdout(chunk: string): void {
    this.buffer += chunk;

    while (true) {
      const newlineIndex = this.buffer.indexOf("\n");
      if (newlineIndex === -1) break;
      const line = this.buffer.slice(0, newlineIndex).trim();
      this.buffer = this.buffer.slice(newlineIndex + 1);

      if (!line) continue;

      let data: any = null;
      try {
        data = JSON.parse(line);
      } catch (error) {
        if (this.debug) {
          this.emit("debug", `Linha nao-JSON do MCP: ${line}`);
        }
        continue;
      }

      const id = data?.id;
      if (!id || !this.pending.has(id)) {
        if (this.debug) {
          this.emit("debug", `Resposta MCP sem request pendente: ${line}`);
        }
        continue;
      }

      const pending = this.pending.get(id);
      if (!pending) continue;
      clearTimeout(pending.timeout);
      this.pending.delete(id);

      if (data.ok) {
        pending.resolve(data.output);
      } else {
        const message = data?.error?.message ?? "Erro MCP";
        pending.reject(new Error(message));
      }
    }
  }

  private failAllPending(error: Error): void {
    for (const [id, pending] of this.pending.entries()) {
      clearTimeout(pending.timeout);
      pending.reject(error);
      this.pending.delete(id);
    }
  }
}
