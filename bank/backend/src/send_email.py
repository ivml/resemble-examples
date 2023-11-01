import logging

logging.basicConfig(level=logging.INFO)

async def send_email(message_body: str):
    # We're not actually going to send an email here; but you could!
    #
    # If you do send real emails, please be sure to use an idempotent API, since
    # (like in any well-written distributed system) this call may be retried in
    # case of errors.
    logging.info(f"Sending email:\n====\n{message_body}\n====")
