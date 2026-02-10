import type { Evidence } from "./types.js";
import { formatLines } from "./utils.js";

export const DEFAULT_SYSTEM_PROMPT = `Voce e um assistente especializado em analisar codigo-fonte.
Responda as perguntas do usuario baseando-se APENAS no contexto fornecido.
Se a informacao nao estiver no contexto, diga que nao encontrou essa informacao no codigo indexado.
Seja conciso e direto. Responda em portugues brasileiro.`;

export function buildRagPrompt(question: string, evidences: Evidence[]): { system: string; user: string } {
  const contextParts = evidences.map((evidence, index) => {
    const lines = formatLines(evidence.startLine, evidence.endLine);
    const snippet = evidence.snippet || "[conteudo nao disponivel]";
    return `### Arquivo ${index + 1}: ${evidence.path} (linhas ${lines})\n\n\`\`\`\n${snippet}\n\`\`\``;
  });

  const contextText = contextParts.join("\n\n");
  const user = `## Contexto do codigo-fonte:\n\n${contextText}\n\n## Pergunta:\n${question}\n\n## Resposta:`;

  return { system: DEFAULT_SYSTEM_PROMPT, user };
}
