#!/usr/bin/env node

import path from "node:path";
import process from "node:process";

import { Command } from "commander";
import { render } from "ink";
import React from "react";

import { McpClient } from "./mcp-client.js";
import { embedText, streamChat } from "./ollama.js";
import { buildRagPrompt } from "./rag.js";
import { ChatApp } from "./tui.js";
import type { AskConfig, Evidence } from "./types.js";
import {
  clamp,
  curateEvidences,
  findRepoRoot,
  formatLines,
  hasUsableSnippet,
  isSafeRelativePath,
  matchesLanguage,
  parseCommandLine,
  splitSnippet,
} from "./utils.js";

const DEFAULT_TOPK = 10;
const DEFAULT_TIMEOUT_MS = 120_000;
const DEFAULT_OLLAMA_URL = "http://localhost:11434";
const DEFAULT_EMBEDDING_MODEL = "manutic/nomic-embed-code";
const DEFAULT_LLM_MODEL = "gpt-oss:latest";
const MAX_EVIDENCE_LINES = 16;
const MIN_EVIDENCE_SCORE = 0.6;
const MAX_VISIBLE_EVIDENCES = 3;
const MAX_SNIPPET_ENRICH = 5;

const program = new Command();

program
  .name("code-compass")
  .description("CLI do Code Compass")
  .version("0.1.0");

program
  .command("ask")
  .description("Chat com o Code Compass (interativo ou one-shot)")
  .argument("[question...]", "Pergunta para modo one-shot")
  .option("--topk <n>", "Numero de evidencias", String(DEFAULT_TOPK))
  .option("--pathPrefix <prefix>", "Filtro por prefixo de path")
  .option("--language <lang>", "Filtro por linguagem/extensao")
  .option("--repo <name>", "Filtro por repo (nao suportado no MVP)")
  .option("--debug", "Debug do MCP e HTTP", false)
  .option("--mcp-command <cmd>", "Comando para iniciar MCP (ex: 'node apps/mcp-server/dist/main.js --transport stdio')")
  .option("--timeout-ms <ms>", "Timeout por request (ms)")
  .action(async (questionParts: string[], options) => {
    const question = Array.isArray(questionParts) ? questionParts.join(" ").trim() : "";
    const config = resolveConfig(options);

    if (!question) {
      render(React.createElement(ChatApp, { config }));
      return;
    }

    await runOneShot(question, config);
  });

program.parseAsync(process.argv).catch((error) => {
  console.error(`Erro: ${(error as Error).message}`);
  process.exitCode = 1;
});

function resolveConfig(options: Record<string, string | boolean | undefined>): AskConfig {
  const topK = Number(options.topk ?? DEFAULT_TOPK);
  const timeoutMs = Number(options.timeoutMs ?? process.env.CODE_COMPASS_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);

  const { command, args } = resolveMcpCommand(options.mcpCommand as string | undefined);

  return {
    topK: Number.isFinite(topK) ? topK : DEFAULT_TOPK,
    pathPrefix: options.pathPrefix ? String(options.pathPrefix).trim() : undefined,
    language: options.language ? String(options.language).trim() : undefined,
    repo: options.repo ? String(options.repo).trim() : undefined,
    debug: Boolean(options.debug),
    ollamaUrl: process.env.OLLAMA_URL ?? DEFAULT_OLLAMA_URL,
    embeddingModel: process.env.EMBEDDING_MODEL ?? DEFAULT_EMBEDDING_MODEL,
    llmModel: process.env.LLM_MODEL ?? DEFAULT_LLM_MODEL,
    mcpCommand: [command, ...args],
    requestTimeoutMs: Number.isFinite(timeoutMs) ? timeoutMs : DEFAULT_TIMEOUT_MS,
  };
}

function resolveMcpCommand(mcpOverride?: string): { command: string; args: string[] } {
  const raw = (mcpOverride ?? process.env.MCP_COMMAND ?? "").trim();
  if (raw) {
    return parseCommandLine(raw);
  }

  const repoRoot = findRepoRoot(process.cwd()) ?? process.cwd();
  const entry = path.join(repoRoot, "apps/mcp-server/dist/main.js");
  return { command: "node", args: [entry, "--transport", "stdio"] };
}

async function runOneShot(question: string, config: AskConfig): Promise<void> {
  const client = new McpClient({
    command: config.mcpCommand[0],
    args: config.mcpCommand.slice(1),
    env: process.env,
    debug: config.debug,
  });

  if (config.debug) {
    client.on("debug", (line) => {
      process.stderr.write(`[debug] ${line}\n`);
    });
  }

  client.start();

  try {
    const vector = await embedText(config.ollamaUrl, config.embeddingModel, question, {
      timeoutMs: config.requestTimeoutMs,
    });

    const searchResponse = await client.searchCode(
      {
        query: question,
        topK: clamp(config.topK, 1, 20),
        pathPrefix: config.pathPrefix,
        vector,
      },
      config.requestTimeoutMs,
    );

    const rawResults = searchResponse?.results ?? [];
    const filteredResults = rawResults.filter((result) =>
      matchesLanguage(result.path ?? "", config.language),
    );

    if (config.repo) {
      process.stderr.write("Aviso: filtro --repo ainda nao e suportado pelo MCP search_code.\n");
    }

    if (filteredResults.length === 0) {
      console.log("Sem evidencia suficiente. Tente refinar a pergunta ou usar --pathPrefix/--language.");
      return;
    }

    const evidences: Evidence[] = filteredResults.map((result) => ({
      path: result.path,
      startLine: result.startLine ?? null,
      endLine: result.endLine ?? null,
      score: result.score,
      snippet: splitSnippet(result.snippet ?? "", MAX_EVIDENCE_LINES),
    }));

    await enrichMissingSnippets(evidences, client, config.requestTimeoutMs);

    const curated = curateEvidences(evidences, {
      minScore: MIN_EVIDENCE_SCORE,
      maxVisible: MAX_VISIBLE_EVIDENCES,
    });

    if (curated.visible.length === 0) {
      console.log(
        "Sem evidencia suficiente para responder com confianca. Tente refinar a pergunta, usar --pathPrefix/--language, ou revisar os resultados com --topk maior.",
      );
      return;
    }

    const { system, user } = buildRagPrompt(question, curated.visible);

    process.stdout.write("Resposta:\n");
    await streamChat(
      config.ollamaUrl,
      config.llmModel,
      system,
      user,
      (chunk) => {
        process.stdout.write(chunk);
      },
      { timeoutMs: config.requestTimeoutMs },
    );
    process.stdout.write("\n\nEvidencias:\n");

    curated.visible.forEach((evidence, index) => {
      const lines = formatLines(evidence.startLine, evidence.endLine);
      process.stdout.write(
        `[${index + 1}] ${evidence.path}:${lines} (${evidence.score.toFixed(3)})\n`,
      );
      const snippetLines = evidence.snippet.split("\n");
      snippetLines.forEach((snippetLine) => {
        process.stdout.write(`    ${snippetLine}\n`);
      });
    });
  } catch (error) {
    console.error(`Erro no ask: ${(error as Error).message}`);
  } finally {
    client.close();
  }
}

async function enrichMissingSnippets(
  evidences: Evidence[],
  client: McpClient,
  timeoutMs: number,
): Promise<void> {
  let enrichedCount = 0;

  for (const evidence of evidences) {
    if (enrichedCount >= MAX_SNIPPET_ENRICH) {
      break;
    }
    if (hasUsableSnippet(evidence.snippet)) {
      continue;
    }
    if (!isSafeRelativePath(evidence.path)) {
      continue;
    }

    const startLine = evidence.startLine ?? 1;
    const endLine = evidence.endLine ?? startLine + 50;

    try {
      const file = await client.openFile(
        {
          path: evidence.path,
          startLine,
          endLine,
        },
        timeoutMs,
      );

      const snippet = splitSnippet(file.text ?? "", MAX_EVIDENCE_LINES).trim();
      if (snippet) {
        evidence.snippet = snippet;
        evidence.startLine = file.startLine;
        evidence.endLine = file.endLine;
        enrichedCount += 1;
      }
    } catch {
      // Mantem snippet original quando open_file falhar
    }
  }
}
