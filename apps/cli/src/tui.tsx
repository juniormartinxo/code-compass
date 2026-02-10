import React, { useEffect, useMemo, useRef, useState } from "react";
import { Box, Spacer, Text, useApp, useInput } from "ink";

import { McpClient } from "./mcp-client.js";
import type { AskConfig, Evidence, OpenFileResponse } from "./types.js";
import { isSafeRelativePath } from "./utils.js";

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  evidences?: Evidence[];
};

type ChatAppProps = {
  config: AskConfig;
};

type Status = {
  mcp: "connected" | "disconnected" | "error";
  rag: "ok" | "error" | "unknown";
};

type SlashCommand = {
  command: string;
  description: string;
  template: string;
};

const SLASH_COMMANDS: SlashCommand[] = [
  { command: "/help", description: "Mostrar ajuda", template: "/help" },
  { command: "/clear", description: "Limpar chat", template: "/clear" },
  { command: "/config", description: "Mostrar configuracao ativa", template: "/config" },
  { command: "/sources", description: "Mostrar fontes da ultima resposta", template: "/sources" },
  { command: "/open", description: "Abrir trecho de arquivo", template: "/open " },
  { command: "/exit", description: "Sair do chat", template: "/exit" },
  { command: "/quit", description: "Sair do chat", template: "/quit" },
];

export function ChatApp({ config }: ChatAppProps): JSX.Element {
  const { exit } = useApp();
  const columns = process.stdout.columns ?? 120;
  const rows = process.stdout.rows ?? 40;
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [cursor, setCursor] = useState(0);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [status, setStatus] = useState<Status>({
    mcp: "disconnected",
    rag: "unknown",
  });
  const [activity, setActivity] = useState<string>("");
  const [lastEvidences, setLastEvidences] = useState<Evidence[]>([]);
  const [scrollOffset, setScrollOffset] = useState(0);

  // Auto-scroll to bottom when new messages appear
  useEffect(() => {
    // Force reset on new messages to keep chat flowing like a standard terminal
    if (streaming) {
        setScrollOffset(0);
    }
  }, [messages.length, streaming]);
  const [commandSelection, setCommandSelection] = useState(0);

  const mcpRef = useRef<McpClient | null>(null);

  const slashState = useMemo(() => {
    const trimmed = input.trimStart();
    if (!trimmed.startsWith("/")) {
      return { active: false, items: [] as SlashCommand[] };
    }

    const token = trimmed.split(/\s+/, 1)[0];
    const query = token.slice(1).toLowerCase();
    const items = SLASH_COMMANDS.filter((item) =>
      item.command.slice(1).toLowerCase().startsWith(query),
    );
    return { active: true, items };
  }, [input]);

  useEffect(() => {
    setCommandSelection(0);
  }, [input]);

  useEffect(() => {
    const client = new McpClient({
      command: config.mcpCommand[0],
      args: config.mcpCommand.slice(1),
      env: process.env,
      debug: config.debug,
    });

    client.on("exit", () => setStatus((prev) => ({ ...prev, mcp: "disconnected" })));
    client.on("error", () => setStatus((prev) => ({ ...prev, mcp: "error" })));
    client.on("debug", (line) => {
      if (config.debug) {
        pushSystemMessage(`[debug] ${line}`);
      }
    });

    client.start();
    mcpRef.current = client;
    setStatus((prev) => ({ ...prev, mcp: "connected" }));

    return () => client.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pushMessage = (message: Message) => {
    setMessages((prev) => [...prev, message]);
  };

  const pushSystemMessage = (text: string) => {
    pushMessage({ id: `sys-${Date.now()}`, role: "system", text });
  };

  const resetHistory = () => {
    setHistoryIndex(null);
  };

  const handleSubmit = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;

    setHistory((prev) => [...prev, trimmed]);
    resetHistory();

    if (trimmed.startsWith("/")) {
      await handleCommand(trimmed);
      return;
    }

    pushMessage({ id: `user-${Date.now()}`, role: "user", text: trimmed });
    await handleAsk(trimmed);
  };

  const handleCommand = async (commandText: string) => {
    const [command, ...rest] = commandText.slice(1).split(" ");
    const args = rest.join(" ");

    switch (command) {
      case "help":
        pushSystemMessage(
          [
            "Comandos disponiveis:",
            "/help - mostra esta ajuda",
            "/exit - sair do chat",
            "/quit - sair do chat",
            "/clear - limpar conversa",
            "/config - mostrar config ativa",
            "/open <path>:<start>-<end> - abrir trecho",
            "/sources - reimprimir evidencias da ultima resposta",
          ].join("\n"),
        );
        break;
      case "exit":
      case "quit":
        exit();
        break;
      case "clear":
        setMessages([]);
        setLastEvidences([]);
        setStreaming(false);
        setStreamText("");
        setActivity("");
        setInput("");
        setCursor(0);
        setHistoryIndex(null);
        if (process.stdout.isTTY) {
          process.stdout.write("\u001Bc");
        }
        break;
      case "config":
        pushSystemMessage(formatConfig(config));
        break;
      case "sources":
        if (lastEvidences.length === 0) {
          pushSystemMessage("Sem evidencias disponiveis.");
        } else {
          pushMessage({
            id: `sources-${Date.now()}`,
            role: "assistant",
            text: "Evidencias (ultima resposta):",
            evidences: lastEvidences,
          });
        }
        break;
      case "open":
        if (!args) {
          pushSystemMessage("Uso: /open <path>:<start>-<end>");
          break;
        }
        await handleOpen(args);
        break;
      default:
        pushSystemMessage(`Comando desconhecido: /${command}`);
        break;
    }
  };

  const handleOpen = async (target: string) => {
    const match = /^(.*?):(\d+)(?:-(\d+))?$/.exec(target.trim());
    if (!match) {
      pushSystemMessage("Formato invalido. Use /open <path>:<start>-<end>");
      return;
    }

    const path = match[1];
    const startLine = Number(match[2]);
    const endLine = match[3] ? Number(match[3]) : startLine + 50;

    if (!isSafeRelativePath(path)) {
      pushSystemMessage("Path invalido (bloqueado por seguranca). Use paths relativos.");
      return;
    }

    const client = mcpRef.current;
    if (!client) {
      pushSystemMessage("MCP nao conectado.");
      return;
    }

    try {
      setActivity("open_file");
      const response = await client.openFile(
        {
          path,
          startLine,
          endLine,
        },
        config.requestTimeoutMs,
      );

      pushOpenFileMessage(response);
    } catch (error) {
      pushSystemMessage(`Erro ao abrir arquivo: ${(error as Error).message}`);
    } finally {
      setActivity("");
    }
  };

  const pushOpenFileMessage = (response: OpenFileResponse) => {
    const header = `Trecho ${response.path}:${response.startLine}-${response.endLine}`;
    const text = response.text.trimEnd();
    const body = text ? `${header}\n${text}` : `${header}\n(vazio)`;
    pushMessage({ id: `open-${Date.now()}`, role: "assistant", text: body });
  };

  const handleAsk = async (question: string) => {
    const client = mcpRef.current;
    if (!client) {
      pushSystemMessage("MCP nao conectado.");
      return;
    }

    setStreaming(true);
    setStreamText("");

    try {
      setActivity("ask_code");

      if (config.repo) {
        pushSystemMessage("Aviso: filtro --repo ainda nao e suportado pelo MCP ask_code.");
      }

      const response = await client.askCode(
        {
          query: question,
          topK: config.topK,
          pathPrefix: config.pathPrefix,
          language: config.language,
          minScore: config.minScore,
          llmModel: config.llmModel,
        },
        config.requestTimeoutMs,
      );

      const evidences = response.evidences ?? [];
      setLastEvidences(evidences);
      setStatus((prev) => ({ ...prev, rag: "ok" }));

      pushMessage({
        id: `assistant-${Date.now()}`,
        role: "assistant",
        text: response.answer?.trim() || "(sem resposta)",
        evidences,
      });
    } catch (error) {
      setStatus((prev) => ({ ...prev, rag: "error" }));
      pushSystemMessage(`Erro no ask: ${(error as Error).message}`);
    } finally {
      setStreaming(false);
      setStreamText("");
      setActivity("");
    }
  };

  useInput((inputValue, key) => {
    // Scroll
    if (key.pageUp) {
      setScrollOffset((prev) => prev + 5);
      return;
    }
    if (key.pageDown) {
      setScrollOffset((prev) => Math.max(0, prev - 5));
      return;
    }

    // Exit
    if (key.ctrl && inputValue === "c") {
      exit();
      return;
    }

    // Submit / Newline
    if (key.return) {
      // Slash command autocomplete (Enter)
      if (slashState.active && slashState.items.length > 0) {
        const command = slashState.items[Math.min(commandSelection, slashState.items.length - 1)];
        const trimmedInput = input.trim();
        const isOnlyCommandToken = /^\/[^\s]*$/.test(trimmedInput);
        const hasExactCommand = SLASH_COMMANDS.some((item) => item.command === trimmedInput);
        
        // Autocomplete if it's partial or matches a template with args
        if (isOnlyCommandToken && (!hasExactCommand || command.template.endsWith(" "))) {
           setInput(command.template);
           setCursor(command.template.length);
           return;
        }
      }

      if (key.shift || key.ctrl) {
        insertText("\n");
        return;
      }

      const value = input.trimEnd();
      if (value) {
        handleSubmit(value).catch((error) => {
          pushSystemMessage(`Erro inesperado: ${(error as Error).message}`);
        });
      }
      setInput("");
      setCursor(0);
      setScrollOffset(0);
      return;
    }

    // Tab autocomplete
    if (key.tab && slashState.active && slashState.items.length > 0) {
      const command = slashState.items[Math.min(commandSelection, slashState.items.length - 1)];
      setInput(command.template);
      setCursor(command.template.length);
      return;
    }

    // Navigation
    if (key.upArrow) {
      // Navigate slash menu
      if (slashState.active && slashState.items.length > 0) {
        setCommandSelection((prev) =>
          prev <= 0 ? slashState.items.length - 1 : prev - 1,
        );
        return;
      }
      // Navigate history
      if (history.length === 0) return;
      const nextIndex = historyIndex === null ? history.length - 1 : Math.max(0, historyIndex - 1);
      setHistoryIndex(nextIndex);
      const nextValue = history[nextIndex] ?? "";
      setInput(nextValue);
      setCursor(nextValue.length);
      return;
    }

    if (key.downArrow) {
      if (slashState.active && slashState.items.length > 0) {
        setCommandSelection((prev) =>
          prev >= slashState.items.length - 1 ? 0 : prev + 1,
        );
        return;
      }
      if (history.length === 0) return;
      const nextIndex = historyIndex === null ? history.length - 1 : historyIndex + 1;
      if (nextIndex >= history.length) {
        setHistoryIndex(null);
        setInput("");
        setCursor(0);
        return;
      }
      setHistoryIndex(nextIndex);
      const nextValue = history[nextIndex] ?? "";
      setInput(nextValue);
      setCursor(nextValue.length);
      return;
    }

    if (key.leftArrow) {
      setCursor((prev) => Math.max(0, prev - 1));
      return;
    }

    if (key.rightArrow) {
      setCursor((prev) => Math.min(input.length, prev + 1));
      return;
    }

    // Edit
    if (key.backspace || key.delete) {
      if (key.delete && cursor < input.length) {
        setInput((prev) => prev.slice(0, cursor) + prev.slice(cursor + 1));
        return;
      }
      if (cursor > 0) {
        setInput((prev) => prev.slice(0, cursor - 1) + prev.slice(cursor));
        setCursor((prev) => Math.max(0, prev - 1));
      }
      return;
    }

    // Evidence shortcut
    if (inputValue >= "1" && inputValue <= "9" && input.length === 0) {
      const index = Number(inputValue) - 1;
      const evidence = lastEvidences[index];
      if (evidence) {
        const start = evidence.startLine ?? 1;
        const end = evidence.endLine ?? start + 50;
        handleOpen(`${evidence.path}:${start}-${end}`).catch(() => null);
      }
      return;
    }

    if (inputValue) {
      insertText(inputValue);
    }
  });

  const insertText = (text: string) => {
    setInput((prev) => prev.slice(0, cursor) + text + prev.slice(cursor));
    setCursor((prev) => prev + text.length);
  };

  /* New Rendering Logic - Line based for Scrolling */
  const headerHeight = 3; 
  const inputHeight = 4; // Approx with border
  const bodyHeight = Math.max(0, rows - headerHeight - inputHeight);
  
  const allLines = useMemo(() => {
    const list = [...messages];
    if (streaming) {
      list.push({
        id: "streaming",
        role: "assistant",
        text: streamText || "...",
      });
    }

    const rendered: React.ReactNode[] = [];
    
    // Helper to add spacing
    const addSpacer = () => rendered.push(<Box key={`spacer-${rendered.length}`} height={1} />);

    list.forEach((msg, msgIndex) => {
        const msgLines = renderMessageToLines(msg, columns, msgIndex);
        rendered.push(...msgLines);
        addSpacer();
    });

    return rendered;
  }, [messages, streaming, streamText, columns]);

  // Calculate slice
  const totalLines = allLines.length;
  // scrollOffset = 0 means show BOTTOM (latest). 
  // scrollOffset > 0 means show older.
  // slice end = totalLines - scrollOffset
  // slice start = slice end - bodyHeight
  
  const safeOffset = Math.max(0, Math.min(scrollOffset, totalLines - bodyHeight));
  const sliceEnd = totalLines - safeOffset;
  const sliceStart = Math.max(0, sliceEnd - bodyHeight);
  
  const visibleSlice = allLines.slice(sliceStart, sliceEnd);
  const llmLabel = formatModelLabel(config.llmModel, Math.max(16, Math.floor(columns * 0.25)));

  return (
    <Box flexDirection="column" height={rows} width={columns}>
      {/* Header */}
      <Box 
        borderStyle="round" 
        borderColor={activity ? "yellow" : "cyan"} 
        paddingX={1} 
        justifyContent="space-between"
        flexShrink={0}
      >
        <Text color="cyan" bold>CODE COMPASS</Text>
        <Box>
          {activity ? (
            <Text color="yellow">⟳ {activity}...</Text> 
          ) : (
            <>
              <Text>MCP: </Text>
              <Text color={status.mcp === "connected" ? "green" : "red"}>{status.mcp}</Text>
              <Text color="gray"> | </Text>
              <Text>RAG: </Text>
              <Text color={status.rag === "ok" ? "green" : status.rag === "error" ? "red" : "gray"}>
                {status.rag}
              </Text>
              <Text color="gray"> | </Text>
              <Text>LLM: </Text>
              <Text color="cyan">{llmLabel}</Text>
            </>
          )}
        </Box>
      </Box>

      {/* Message History */}
      <Box flexDirection="column" height={bodyHeight} paddingX={1} justifyContent="flex-start" overflow="hidden">
          {visibleSlice.length === 0 && messages.length === 0 && !streaming && (
            <Box alignItems="center" justifyContent="center" height="100%">
              <Text color="grey">Digite uma pergunta para começar...</Text>
            </Box>
          )}
          {visibleSlice.map((lineNode, i) => (
             <Box key={i}>{lineNode}</Box>
          ))}
      </Box>

      {/* Input Area */}
      <Box flexDirection="column" flexShrink={0}>
        {slashState.active && slashState.items.length > 0 && (
          <Box borderStyle="round" borderColor="magenta" flexDirection="column" paddingX={1}>
            <Text color="magenta" bold>Comandos</Text>
            {slashState.items.slice(0, 6).map((item, index) => {
              const selected = index === Math.min(commandSelection, slashState.items.length - 1);
              return (
                <Text key={item.command} color={selected ? "yellow" : "gray"}>
                  {selected ? "> " : "  "}
                  {item.command} - {item.description}
                </Text>
              );
            })}
            <Text color="grey" dimColor>Setas: navegar | Tab/Enter: completar</Text>
          </Box>
        )}

        <Box 
            borderStyle="round" 
            borderColor={activity ? "grey" : "green"} 
            flexDirection="row"
            paddingX={1}
        >
            <Text color="green"> › </Text>
            <Text>
            {input.slice(0, cursor)}
            <Text inverse color="white">{input[cursor] || " "}</Text>
            {input.slice(cursor + 1)}
            </Text>
        </Box>
        
        <Box paddingX={2} justifyContent="space-between">
          <Spacer />
            <Text color="yellowBright" dimColor>Enter: enviar | Shift+Enter: nova linha | PgUp/PgDn: scroll</Text>
            <Text color="yellowBright" dimColor>/help para comandos</Text>
        </Box>
      </Box>
    </Box>
  );
}

function renderMessageToLines(message: Message, columns: number, msgIndex: number): React.ReactNode[] {
    const isUser = message.role === "user";
    const isSystem = message.role === "system";
    // Adjust width for padding/borders.
    const maxContentWidth = Math.max(20, Math.floor(columns * 0.95) - 4); 
    
    if (isSystem) {
        return wrapText(message.text, maxContentWidth).map((l, i) => (
            <Box key={`sys-${msgIndex}-${i}`} width="100%" justifyContent="center">
                <Text color="magenta" italic>{l}</Text>
            </Box>
        ));
    }

    const lines: React.ReactNode[] = [];
    const borderColor = isUser ? "green" : "blue";
    const roleColor = isUser ? "green" : "blue";
    
    const title = isUser ? "Dev 🧑‍💻" : "🤖 Compass ";
    const prefix = "╭─";
    const suffix = "─╮";
    //const dashCount = Math.max(0, maxContentWidth - title.length - prefix.length - suffix.length + 2); 
    const align = "flex-start" //isUser ? "flex-end" : "flex-start";
    
    // Header
    lines.push(
        <Box key={`h-${msgIndex}`} justifyContent={align} width="100%" paddingY={1}>
             <Text color={roleColor} bold>{title}</Text>
        </Box>
    );

    // Body
    const textLines = wrapText(message.text, maxContentWidth - 2);
    if (textLines.length === 0) textLines.push(""); 

    textLines.forEach((l, i) => {
        lines.push(
            <Box key={`b-${msgIndex}-${i}`} justifyContent={align} width="100%" paddingX={2}>
               <Text>{l.padEnd(maxContentWidth - 2, " ")}</Text>
            </Box>
        );
    });

    // Evidences
    if (message.evidences && message.evidences.length > 0) {
        lines.push(
            <Box key={`sep-${msgIndex}`} justifyContent={align} width="100%" paddingTop={1} paddingX={2} marginBottom={1}>
                 <Text color="yellow" bold>Evidencias</Text>
            </Box>
        );
        
        message.evidences.forEach((ev, i) => {
             const evTitle = `[${i+1}] ${ev.path}`;
             const evScore = ` (${ev.score.toFixed(2)})`;
             const wrappedTitle = wrapText(evTitle + evScore, maxContentWidth - 2);
             
             wrappedTitle.forEach((tl, ti) => {
                 lines.push(
                    <Box key={`ev-${msgIndex}-${i}-t-${ti}`} justifyContent={align} width="100%" paddingX={2}>
                         <Text color="cyan">{tl.padEnd(maxContentWidth - 2, " ")}</Text>
                    </Box>
                );
             });
             
             // Divider inside box
             //lines.push(
               // <Box key={`ev-${msgIndex}-${i}-div`} justifyContent={align} width="100%" paddingX={2}>
                 //    <Text color="cyanBright">{"─".repeat(maxContentWidth - 2)}</Text>
                //</Box>
            //);

             //const snippetLines = (ev.snippet || "").split('\n');
             //snippetLines.forEach((sl, sli) => {
              //   const wrappedSl = wrapText(sl, maxContentWidth - 2);
               //  wrappedSl.forEach((wsl, wsli) => {
                //    lines.push(
                 //       <Box key={`ev-${msgIndex}-${i}-s-${sli}-${wsli}`} justifyContent={align} width="100%" paddingX={2}>
                  //          <Text color="whiteBright" dimColor>{wsl.padEnd(maxContentWidth - 2, " ")}</Text>
                   //     </Box>
                    //);
                 //});
             //});
        });
    }

    // Footer
    //lines.push(
         //<Box key={`f-${msgIndex}`} justifyContent={align} width="100%">
        //     <Text color={borderColor}>╰{"─".repeat(maxContentWidth)}╯</Text>
      //  </Box>
    //);

    return lines;
}

function wrapText(text: string, maxWidth: number): string[] {
    const lines: string[] = [];
    const paragraphs = text.split('\n');
    
    for (const paragraph of paragraphs) {
        if (paragraph.length <= maxWidth) {
            lines.push(paragraph);
        } else {
            let current = paragraph;
            while (current.length > maxWidth) {
                 let splitIndex = current.lastIndexOf(' ', maxWidth);
                 if (splitIndex === -1 || splitIndex < maxWidth * 0.7) {
                     splitIndex = maxWidth; 
                 }
                 lines.push(current.slice(0, splitIndex));
                 current = current.slice(splitIndex).trimStart();
            }
            if(current) lines.push(current);
        }
    }
    return lines;
}

function formatConfig(config: AskConfig): string {
  return [
    "Config ativa:",
    `MCP command: ${config.mcpCommand.join(" ")}`,
    `LLM_MODEL: ${config.llmModel}`,
    `TOPK: ${config.topK}`,
    `MIN_SCORE: ${config.minScore}`,
    `PATH_PREFIX: ${config.pathPrefix ?? "(nenhum)"}`,
    `LANGUAGE: ${config.language ?? "(nenhum)"}`,
    `REPO: ${config.repo ?? "(nenhum)"}`,
    `DEBUG: ${config.debug ? "on" : "off"}`,
  ].join("\n");
}

function formatModelLabel(model: string, maxLen: number): string {
  const normalized = model.trim();
  if (!normalized) return "(desconhecido)";
  if (normalized.length <= maxLen) return normalized;
  if (maxLen <= 3) return normalized.slice(0, maxLen);
  return `${normalized.slice(0, maxLen - 3)}...`;
}
