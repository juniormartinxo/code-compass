#!/usr/bin/env node

import path from "node:path";
import process from "node:process";

import { Command } from "commander";
import { render } from "ink";
import React from "react";

import { McpClient } from "./mcp-client.js";
import { ChatApp } from "./tui.js";
import type { AskConfig } from "./types.js";
import { findRepoRoot, formatLines, parseCommandLine } from "./utils.js";

const DEFAULT_TOPK = 10;
const DEFAULT_MIN_SCORE = 0.6;
const DEFAULT_TIMEOUT_MS = 120_000;
const DEFAULT_LLM_MODEL = "gpt-oss:latest";

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
  .option("--repo <name>", "Filtro por repo (equivale a scope.repo no MCP)")
  .option("--minScore <n>", "Score minimo para considerar evidencias", String(DEFAULT_MIN_SCORE))
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
  const minScore = Number(options.minScore ?? DEFAULT_MIN_SCORE);
  const timeoutMs = Number(options.timeoutMs ?? process.env.CODE_COMPASS_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);

  const { command, args } = resolveMcpCommand(options.mcpCommand as string | undefined);

  return {
    topK: Number.isFinite(topK) ? topK : DEFAULT_TOPK,
    pathPrefix: options.pathPrefix ? String(options.pathPrefix).trim() : undefined,
    language: options.language ? String(options.language).trim() : undefined,
    repo: options.repo ? String(options.repo).trim() : undefined,
    minScore: Number.isFinite(minScore) ? minScore : DEFAULT_MIN_SCORE,
    debug: Boolean(options.debug),
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
    const response = await client.askCode(
      {
        repo: config.repo,
        query: question,
        topK: config.topK,
        pathPrefix: config.pathPrefix,
        language: config.language,
        minScore: config.minScore,
        llmModel: config.llmModel,
      },
      config.requestTimeoutMs,
    );

    process.stdout.write("Resposta:\n");
    process.stdout.write(`${response.answer}\n`);
    process.stdout.write("\n\nEvidencias:\n");

    response.evidences.forEach((evidence, index) => {
      const lines = formatLines(evidence.startLine, evidence.endLine);
      process.stdout.write(
        `[${index + 1}] ${evidence.path}:${lines} (${evidence.score.toFixed(3)})\n`,
      );
      const snippetLines = evidence.snippet.split("\n");
      snippetLines.forEach((snippetLine) => {
        process.stdout.write(`    ${snippetLine}\n`);
      });
    });

    process.stdout.write(`\nModelo: ${response.meta.llmModel}\n`);
  } catch (error) {
    console.error(`Erro no ask: ${(error as Error).message}`);
  } finally {
    client.close();
  }
}
