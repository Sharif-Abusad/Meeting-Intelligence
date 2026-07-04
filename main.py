# from dotenv import load_dotenv
# from utils.audio_processor import process_input
# from core.transcriber import transcribe_all
# from core.summarizer import summarize, generate_title
# from core.extractor import extract_action_items, extract_key_decisions, extract_questions
# from core.rag_engine import build_rag_chain, ask_question

# load_dotenv()

# def run_pipeline(source: str, language:str = "english") -> dict:
#     print("Starting AI Video Assistant")

#     chunks = process_input(source)

#     transcript = transcribe_all(chunks, language = language)
#     print(f"raw transcription (first 300 characters) {transcript[:300]}")

#     title = generate_title(transcript)

#     summary = summarize(transcript)

#     action_items = extract_action_items(transcript)
#     decisions = extract_key_decisions(transcript)
#     questions = extract_questions(transcript)

#     rag_chain = build_rag_chain(transcript)

#     return {
#         "title": title,
#         "transcript": transcript,
#         "summary": summary,
#         "action_items": action_items,
#         "key_decisions": decisions,
#         "open_questions": questions,
#         "rag_chain": rag_chain,
#     }

# if __name__ == "__main__":
#     # CLI entry point
#     source = input("Enter Youtube URL or local file path: ").strip()
#     language = input("Language (english/hinglish): ").strip() or "english"
#     result = run_pipeline(source=source, language=language)

#     print("\n" + "=" * 60)
#     print(f"📌 Title: {result['title']}")
#     print(f"\n📋 Summary:\n{result['summary']}")
#     print(f"\n✅ Action Items:\n{result['action_items']}")
#     print(f"\n🔑 Key Decisions:\n{result['key_decisions']}")
#     print(f"\n❓ Open Questions:\n{result['open_questions']}")
#     print("=" * 60)

#     # Phase 2 — Chat with your meeting via RAG
#     print("\n💬 Chat with your meeting (type 'exit' to quit)\n")
#     rag_chain = result["rag_chain"]
#     while True:
#         question = input("You: ").strip()
#         if question.lower() in ["exit", "quit", "q"]:
#             print("👋 Goodbye!")
#             break

#         if not question:
#             continue

#         answer = ask_question(rag_chain, question)
#         print(f"\n🤖 Assistant: {answer}\n")

"""
Command-line entry point for the Meeting Intelligence pipeline.

Usage:

    python main.py "meeting.mp4"
    python main.py "https://youtu.be/VIDEO_ID" --language hinglish
    python main.py "meeting.mp3" --output result.json --no-index

Run `python main.py --help` for all options.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.core.exceptions import MeetingIntelligenceError
from app.core.logging_config import configure_logging
from app.core.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe, summarize, and analyze a meeting recording."
    )
    parser.add_argument(
        "source",
        help="Local audio/video file path, or a YouTube URL.",
    )
    parser.add_argument(
        "--language",
        choices=["english", "hinglish"],
        default="english",
        help="Transcription engine to use (default: english).",
    )
    parser.add_argument(
        "--chunk-minutes",
        type=int,
        default=None,
        help="Override the audio chunk length in minutes.",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip building the vector store (disables later Q&A).",
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep downloaded/converted audio artifacts instead of deleting them.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write the JSON result to this file instead of stdout.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        result = run_pipeline(
            source=args.source,
            language=args.language,
            chunk_minutes=args.chunk_minutes,
            build_index=not args.no_index,
            cleanup_audio=not args.keep_audio,
        )
    except MeetingIntelligenceError as exc:
        logger.error("Pipeline failed: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130

    output_json = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        logger.info("Result written to %s", args.output)
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
