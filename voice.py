import asyncio

MODEL_PATH = "vi_VN-vivos-x_low.onnx"

async def say(text: str, model_path: str = MODEL_PATH) -> None:
    """
    Asynchronously synthesizes Vietnamese text offline using Piper and plays via aplay.
    """
    # Create piper process piped to aplay
    piper_proc = await asyncio.create_subprocess_exec(
        "piper",
        "--model", model_path,
        "--output-raw",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    
    aplay_proc = await asyncio.create_subprocess_exec(
        "aplay",
        "-r", "22050",
        "-f", "S16_LE",
        "-t", "raw",
        "-q",
        stdin=piper_proc.stdout,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    # Pass text to piper's stdin
    if piper_proc.stdin:
        piper_proc.stdin.write(text.encode("utf-8"))
        await piper_proc.stdin.drain()
        piper_proc.stdin.close()
        await piper_proc.stdin.wait_closed()

    await asyncio.gather(piper_proc.wait(), aplay_proc.wait())


async def main():
    await say("Hệ thống ngoại tuyến đã sẵn sàng hoạt động.")

if __name__ == "__main__":
    asyncio.run(main())