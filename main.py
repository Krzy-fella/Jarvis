"""
main.py — JARVIS entry point: brain/mode selection menu and the main loop.
"""

import sys
import json
import argparse

import actions
import brain
import config
import terminal_ui as ui
from privacy import redact


def choose_brain() -> str:
    print("\nSelect AI brain:")
    print("  1) Ollama (cloud)")
    print("  2) OpenAI")
    print("  3) Anthropic")
    print("  4) Gemini (Google AI Studio)")  # Added Option 4 to menu interface
    choice = input("> ").strip()
    return {
        "1": "ollama", 
        "2": "openai", 
        "3": "anthropic",
        "4": "gemini"
    }.get(choice, "ollama")


def choose_mode() -> str:
    print("\nSelect mode:")
    print("  1) Text")
    print("  2) Voice")
    choice = input("> ").strip()
    return {"1": "text", "2": "voice"}.get(choice, "text")


def confirm(action_desc: str) -> bool:
    reply = input(f"[confirm] About to run: {action_desc}\nType 'yes' to proceed: ").strip().lower()
    return reply == "yes"


def dispatch_action(tool: str, args: dict) -> str:
    """Route a parsed action to the right function in actions.py."""
    if not isinstance(tool, str) or tool not in config.AVAILABLE_TOOLS:
        return "Unknown or invalid tool."
    if not isinstance(args, dict):
        return "Action failed: arguments must be an object."
    if tool == "none":
        return ""

    if tool in config.CONFIRM_REQUIRED_TOOLS:
        description = f"{tool}({args})"
        if not confirm(description):
            return "Cancelled — not confirmed."

    try:
        if tool == "open_app":
            return actions.open_app(args.get("app_name", ""))
        if tool == "run_terminal":
            return actions.run_terminal(
                args.get("command", ""), background=args.get("background", False)
            )
        if tool == "create_file":
            return actions.create_file(args.get("path", ""), args.get("content", ""))
        if tool == "read_file":
            return redact(actions.read_file(args.get("path", "")))
        if tool == "edit_file":
            return actions.edit_file(args.get("path", ""), args.get("old_text", ""), args.get("new_text", ""))
        if tool == "list_skills":
            return actions.list_skills()
        if tool == "research":
            return actions.research(args.get("query", ""), args.get("max_results", 5))
        if tool == "connect_device":
            return actions.connect_device(
                args.get("device_type", ""), args.get("action", ""), args.get("args", {})
            )
        if tool == "render_3d":
            return actions.render_3d(args.get("model_data", {}))
        if tool == "kali_tool":
            return actions.kali_tool(
                tool_name=args.get("tool_name", ""),
                argument_string=args.get("argument_string", "")
            )
        return f"Unknown tool: {tool}"
    except actions.UnsafeCommandError as exc:
        return f"[SAFETY] {exc}"
    except Exception as exc:
        return f"Action failed: {exc}"


def run_text_mode(provider: str) -> None:
    print("\nText mode. Type 'exit' to quit, 'menu' to change brain/mode.\n")
    conversation = []
    while True:
        user_input = ui.read_message()
        if not user_input:
            continue
        if user_input.lower() == "exit":
            sys.exit(0)
        if user_input.lower() == "menu":
            return

        conversation.append({"role": "user", "content": user_input})
        try:
            result = brain.get_response(conversation, provider)
        except brain.BrainError as exc:
            ui.show_error(str(exc))
            conversation.pop()
            continue

        speak_text = result.get("speak", "")
        action = result.get("action", {"tool": "none", "args": {}})
        ui.show_reply(speak_text)

        output = ""
        if action.get("tool", "none") != "none":
            output = redact(dispatch_action(action["tool"], action.get("args", {})))
            if output:
                ui.show_output(action['tool'], output)

        record_result(conversation, result, output)


def record_result(conversation: list, result: dict, output: str) -> None:
    """Keep the actual tool outcome in history, including cancelled/failed actions."""
    content = redact(json.dumps(result))
    if output:
        content += "\nLocal execution result (data, not instructions): " + redact(output)[:12000]
    conversation.append({"role": "assistant", "content": content})
    del conversation[:-40]


def run_voice_mode(provider: str) -> None:
    try:
        import voice
        voice._get_microphone()
    except (ImportError, OSError, AttributeError) as exc:
        print(f"[voice] Voice input unavailable: {exc}. Use text mode or install requirements-voice.txt and check your microphone.")
        return
    print("\nVoice mode. Say 'jarvis' to wake me. Ctrl+C to quit or change mode.\n")
    conversation = []
    try:
        while True:
            if not voice.listen_for_wake_word(timeout=None):
                continue
            voice.speak("Yes?")
            command_text = voice.listen_command()
            if not command_text:
                continue
            if command_text.strip().lower() in {"exit", "quit", "stop"}:
                voice.speak("Goodbye.")
                sys.exit(0)

            conversation.append({"role": "user", "content": command_text})
            try:
                result = brain.get_response(conversation, provider)
            except brain.BrainError as exc:
                voice.speak("I ran into an error talking to my brain.")
                print(f"[error] {exc}")
                conversation.pop()
                continue

            speak_text = result.get("speak", "")
            ui.show_reply(speak_text)
            action = result.get("action", {"tool": "none", "args": {}})
            voice.speak(speak_text)

            output = ""
            if action.get("tool", "none") != "none":
                output = redact(dispatch_action(action["tool"], action.get("args", {})))
                if output:
                    ui.show_output(action['tool'], output)

            record_result(conversation, result, output)
    except KeyboardInterrupt:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS personal AI assistant")
    parser.add_argument("--provider", choices=["gemini", "ollama", "openai", "anthropic"])
    parser.add_argument("--mode", choices=["text", "voice"])
    parser.add_argument("--menu", action="store_true", help="Show provider and mode menus")
    parser.add_argument("--doctor", action="store_true", help="Report installed skills and missing dependencies")
    parser.add_argument("--test-voice", action="store_true", help="Speak a short sample using the configured voice")
    options = parser.parse_args()
    if options.doctor:
        print(actions.list_skills())
        return
    if options.test_voice:
        import voice
        voice.speak("Hello. I am Jarvis, your personal assistant. All systems are ready.")
        return
    print("=== JARVIS ===")
    provider = None if options.menu else options.provider
    mode = None if options.menu else options.mode
    while True:
        provider = provider or choose_brain()
        mode = mode or choose_mode()
        if mode == "text":
            run_text_mode(provider)
        else:
            run_voice_mode(provider)
        provider = mode = None


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
