import sys
import asyncio
import edge_tts

# High-quality neural Vietnamese male voice
VOICE_NAME = "vi-VN-NamMinhNeural"

async def say(text: str, voice: str = VOICE_NAME) -> None:
    """
    Streams high-quality neural Vietnamese audio directly from Edge TTS to aplay.
    """
    communicate = edge_tts.Communicate(text, voice)

    # Launch aplay expecting MP3/decoded audio, or pipe into mpv
    proc = await asyncio.create_subprocess_exec(
        "mpv",
        "--no-terminal",
        "--really-quiet",
        "-",
        stdin=asyncio.subprocess.PIPE,
    )

    try:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and proc.stdin:
                proc.stdin.write(chunk["data"])
                await proc.stdin.drain()
    finally:
        if proc.stdin:
            proc.stdin.close()
            await proc.stdin.wait_closed()
        await proc.wait()

if __name__ == "__main__":
    test_phrase = sys.argv[1] if len(sys.argv) > 1 else "Xin chào, hệ thống nhận diện khuôn mặt đã sẵn sàng hoạt động."
    print(f"[TEST] Phát âm thanh giọng nam (Edge-TTS): \"{test_phrase}\"")
    try:
        asyncio.run(say(test_phrase))
    except KeyboardInterrupt:
        print("\n[TEST] Dừng phát âm.")