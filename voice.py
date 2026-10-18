import asyncio
import subprocess

MODEL_PATH = "vi_VN-vivos-x_low.onnx"

async def say(text: str, model_path: str = MODEL_PATH) -> None:
    """
    Synthesizes Vietnamese text offline with Piper and pipes raw audio to aplay.
    """
    # 1. Start piper process
    piper_proc = await asyncio.create_subprocess_exec(
        "piper",
        "--model", model_path,
        "--output-raw",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    # 2. Start aplay process reading from PIPE
    aplay_proc = await asyncio.create_subprocess_exec(
        "aplay",
        "-r", "22050",
        "-f", "S16_LE",
        "-t", "raw",
        "-q",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    async def pipe_audio():
        # Read from Piper's stdout stream and write into aplay's stdin stream
        try:
            while True:
                chunk = await piper_proc.stdout.read(4096)
                if not chunk:
                    break
                if aplay_proc.stdin:
                    aplay_proc.stdin.write(chunk)
                    await aplay_proc.stdin.drain()
        finally:
            if aplay_proc.stdin:
                aplay_proc.stdin.close()
                await aplay_proc.stdin.wait_closed()

    # Feed input text to Piper
    if piper_proc.stdin:
        piper_proc.stdin.write(text.encode("utf-8"))
        await piper_proc.stdin.drain()
        piper_proc.stdin.close()
        await piper_proc.stdin.wait_closed()

    # Stream the data between processes and wait for completion
    await asyncio.gather(pipe_audio(), piper_proc.wait(), aplay_proc.wait())