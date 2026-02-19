from __future__ import annotations


def _patch_toad_slash_aliases() -> None:
    from toad.slash_command import SlashCommand
    from toad.widgets.conversation import Conversation

    if getattr(Conversation, "_code_compass_alias_patch", False):
        return

    original_build = Conversation._build_slash_commands
    original_slash_command = Conversation.slash_command

    def patched_build(self: Conversation) -> list[SlashCommand]:
        slash_commands = list(original_build(self))
        slash_commands.extend(
            [
                SlashCommand(
                    "/clear",
                    "Limpa a janela da conversa",
                    "<opcional: número de linhas para manter>",
                ),
                SlashCommand("/close", "Fecha a sessão atual"),
            ]
        )
        deduplicated = {
            slash_command.command: slash_command for slash_command in slash_commands
        }
        return sorted(
            deduplicated.values(),
            key=lambda slash_command: slash_command.command,
        )

    async def patched_slash_command(self: Conversation, text: str) -> bool:
        command = ""
        parameters = ""
        if text.startswith("/"):
            command, _, parameters = text[1:].partition(" ")

        if command == "clear":
            mapped = "/toad:clear"
            if parameters.strip():
                mapped = f"/toad:clear {parameters}"
            return await original_slash_command(self, mapped)

        if command == "close":
            return await original_slash_command(self, "/toad:session-close")

        return await original_slash_command(self, text)

    Conversation._build_slash_commands = patched_build  # type: ignore[assignment]
    Conversation.slash_command = patched_slash_command  # type: ignore[assignment]
    setattr(Conversation, "_code_compass_alias_patch", True)


def main() -> None:
    _patch_toad_slash_aliases()
    from toad.cli import main as toad_main

    toad_main()


if __name__ == "__main__":
    main()
