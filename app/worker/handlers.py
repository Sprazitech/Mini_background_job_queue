import asyncio


async def handle_send_email(payload: dict) -> None:
    await asyncio.sleep(2)
    if payload.get("force_fail"):
        raise ValueError("Simulated email failure")


async def handle_generate_report(payload: dict) -> None:
    await asyncio.sleep(3)
    if payload.get("force_error"):
        raise RuntimeError("Simulated report error")


HANDLERS = {
    "send_email": handle_send_email,
    "generate_report": handle_generate_report,
}
