export type OllamaChatChunk = {
  message?: { content?: string };
  done?: boolean;
};

type OllamaEmbedResponse = {
  embeddings?: number[][];
};

type FetchOptions = {
  timeoutMs?: number;
};

async function readOllamaError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { error?: string; message?: string };
    const detail = payload.error ?? payload.message;
    if (detail) {
      return detail;
    }
  } catch {
    // ignore json parse errors
  }

  try {
    const text = await response.text();
    if (text.trim()) {
      return text.trim().slice(0, 240);
    }
  } catch {
    // ignore read errors
  }

  return "sem detalhes";
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    return response;
  } finally {
    clearTimeout(timeout);
  }
}

export async function embedText(
  ollamaUrl: string,
  model: string,
  text: string,
  options: FetchOptions = {},
): Promise<number[]> {
  const timeoutMs = options.timeoutMs ?? 120_000;
  const response = await fetchWithTimeout(
    `${ollamaUrl.replace(/\/$/, "")}/api/embed`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, input: [text] }),
    },
    timeoutMs,
  );

  if (!response.ok) {
    const detail = await readOllamaError(response);
    throw new Error(`Erro ao gerar embedding (HTTP ${response.status}): ${detail}`);
  }

  const data = (await response.json()) as OllamaEmbedResponse;
  const embeddings = data?.embeddings;
  if (!Array.isArray(embeddings) || embeddings.length === 0) {
    throw new Error("Resposta de embedding invalida do Ollama");
  }

  return embeddings[0] as number[];
}

export async function streamChat(
  ollamaUrl: string,
  model: string,
  systemPrompt: string,
  userMessage: string,
  onChunk: (text: string) => void,
  options: FetchOptions = {},
): Promise<string> {
  const timeoutMs = options.timeoutMs ?? 120_000;
  const response = await fetchWithTimeout(
    `${ollamaUrl.replace(/\/$/, "")}/api/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userMessage },
        ],
        stream: true,
      }),
    },
    timeoutMs,
  );

  if (!response.ok) {
    const detail = await readOllamaError(response);
    throw new Error(`Erro ao chamar LLM (HTTP ${response.status}): ${detail}`);
  }

  if (!response.body) {
    throw new Error("Resposta do Ollama sem stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    let newlineIndex = buffer.indexOf("\n");

    while (newlineIndex !== -1) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);

      if (line) {
        let data: OllamaChatChunk | null = null;
        try {
          data = JSON.parse(line);
        } catch {
          data = null;
        }

        if (data?.message?.content) {
          fullText += data.message.content;
          onChunk(data.message.content);
        }

        if (data?.done) {
          return fullText;
        }
      }

      newlineIndex = buffer.indexOf("\n");
    }
  }

  return fullText;
}
