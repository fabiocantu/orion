"""Stub para envio futuro de e-mail."""


def send_record_email(recipient: str, subject: str, attachment_path: str | None = None) -> dict:
    return {
        "ok": True,
        "message": (
            f"Envio simulado para {recipient}. "
            f"Assunto: {subject}. Anexo: {attachment_path or 'nenhum'}."
        ),
    }
