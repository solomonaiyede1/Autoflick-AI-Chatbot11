
import os
import json

from io import BytesIO

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    Response,
    stream_with_context,
)

from openai import OpenAI
from pypdf import PdfReader

from extensions import db
from models import Conversation, Message


chat_bp = Blueprint("chat", __name__)

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_DOCUMENT_CHARS = 60000
MAX_PAGES = 50


# ==================================================
# OPENAI CONFIGURATION
# ==================================================

def get_openai_client():
    api_key = "key_wphrp9qRKhgzoaeV"

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing from backend/.env"
        )

    return OpenAI(api_key=api_key)


def get_model():
    return "gpt-4o-mini"


SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are Autoflick AI, a helpful, professional "
        "and intelligent AI assistant. Provide clear, "
        "accurate and useful answers. When explaining "
        "technical topics, use practical examples and "
        "step-by-step guidance where appropriate. "
        "If you are uncertain, say so."
    )
}


# ==================================================
# AUTOMATIC CONVERSATION TITLES
# ==================================================

def generate_conversation_title(first_message):

    fallback_title = (
        " ".join((first_message or "New Chat").split())[:60]
        or "New Chat"
    )

    try:
        client = get_openai_client()

        response = client.chat.completions.create(
            model=get_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Create a concise, descriptive title "
                        "for an AI chat conversation. Return "
                        "only the title, ideally 3 to 6 words. "
                        "Do not use quotation marks or punctuation."
                    )
                },
                {
                    "role": "user",
                    "content": first_message[:1500]
                }
            ],
            temperature=0.3,
            max_tokens=20
        )

        title = (
            response.choices[0].message.content or ""
        ).strip()

        title = title.strip(" \"'`\n\r.!?")
        title = " ".join(title.split())

        return title[:60] if title else fallback_title

    except Exception:
        current_app.logger.exception(
            "Conversation title generation failed."
        )
        return fallback_title


# ==================================================
# CONVERSATION HELPERS
# ==================================================

def create_conversation(first_message="New Chat"):

    conversation = Conversation(
        title=generate_conversation_title(first_message)
    )

    db.session.add(conversation)
    db.session.flush()

    return conversation


def get_or_create_conversation(
    conversation_id,
    first_message
):

    if conversation_id:

        try:
            conversation_id = int(conversation_id)
        except (TypeError, ValueError):
            raise ValueError("Invalid conversation ID.")

        conversation = db.session.get(
            Conversation,
            conversation_id
        )

        if not conversation:
            raise LookupError("Conversation not found.")

        return conversation

    return create_conversation(first_message)


def save_message(conversation, role, content):

    message = Message(
        conversation_id=conversation.id,
        role=role,
        content=content
    )

    db.session.add(message)

    return message


def serialize_message(message):

    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": (
            message.created_at.isoformat()
            if message.created_at else None
        )
    }


def serialize_conversation(conversation):

    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": (
            conversation.created_at.isoformat()
            if conversation.created_at else None
        ),
        "updated_at": (
            conversation.updated_at.isoformat()
            if conversation.updated_at else None
        )
    }


def validate_messages(messages):

    if not isinstance(messages, list) or not messages:
        raise ValueError(
            "A valid messages array is required."
        )

    valid_messages = []

    for item in messages[-20:]:

        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in ("user", "assistant"):
            continue

        if not isinstance(content, str) or not content.strip():
            continue

        valid_messages.append({
            "role": role,
            "content": content.strip()
        })

    if (
        not valid_messages
        or valid_messages[-1]["role"] != "user"
    ):
        raise ValueError(
            "Your latest message must be a user message."
        )

    return valid_messages


# ==================================================
# NORMAL AI CHAT
# ==================================================

@chat_bp.route("/api/chat", methods=["POST"])
def chat():

    data = request.get_json(silent=True) or {}

    try:
        valid_messages = validate_messages(
            data.get("messages")
        )

        conversation = get_or_create_conversation(
            data.get("conversation_id"),
            valid_messages[-1]["content"]
        )

        save_message(
            conversation,
            "user",
            valid_messages[-1]["content"]
        )

        db.session.commit()

        client = get_openai_client()

        response = client.chat.completions.create(
            model=get_model(),
            messages=[SYSTEM_MESSAGE] + valid_messages,
            temperature=0.7
        )

        reply = response.choices[0].message.content

        if not reply:
            raise RuntimeError(
                "The AI returned an empty response."
            )

        save_message(
            conversation,
            "assistant",
            reply
        )

        db.session.commit()

        return jsonify({
            "success": True,
            "reply": reply,
            "model": get_model(),
            "conversation_id": conversation.id
        }), 200

    except (ValueError, LookupError) as error:

        db.session.rollback()

        status_code = (
            404 if isinstance(error, LookupError) else 400
        )

        return jsonify({
            "success": False,
            "error": str(error)
        }), status_code

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Chat request failed."
        )

        return jsonify({
            "success": False,
            "error": (
                "Autoflick AI could not process your message."
            )
        }), 500


# ==================================================
# STREAMING AI CHAT
# ==================================================

@chat_bp.route("/api/chat/stream", methods=["POST"])
def stream_chat():

    data = request.get_json(silent=True) or {}

    try:
        valid_messages = validate_messages(
            data.get("messages")
        )

        conversation = get_or_create_conversation(
            data.get("conversation_id"),
            valid_messages[-1]["content"]
        )

        save_message(
            conversation,
            "user",
            valid_messages[-1]["content"]
        )

        db.session.commit()

        conversation_id = conversation.id

    except (ValueError, LookupError) as error:

        db.session.rollback()

        status_code = (
            404 if isinstance(error, LookupError) else 400
        )

        return jsonify({
            "success": False,
            "error": str(error)
        }), status_code

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to prepare streaming conversation."
        )

        return jsonify({
            "success": False,
            "error": "Unable to start your conversation."
        }), 500

    @stream_with_context
    def generate():

        full_reply = ""

        try:

            client = get_openai_client()

            response = client.chat.completions.create(
                model=get_model(),
                messages=[SYSTEM_MESSAGE] + valid_messages,
                temperature=0.7,
                stream=True
            )

            # Send conversation ID to the frontend.

            yield (
                "event: metadata\n"
                f"data: {json.dumps({'conversation_id': conversation_id})}\n\n"
            )

            # Stream response chunks as they arrive.

            for chunk in response:

                if not chunk.choices:
                    continue

                content = chunk.choices[0].delta.content

                if not content:
                    continue

                full_reply += content

                yield (
                    "event: token\n"
                    f"data: {json.dumps({'content': content})}\n\n"
                )

            if not full_reply.strip():
                raise RuntimeError(
                    "The AI returned an empty response."
                )

            # Save the completed AI response in MySQL.

            saved_conversation = db.session.get(
                Conversation,
                conversation_id
            )

            if not saved_conversation:
                raise RuntimeError(
                    "The conversation no longer exists."
                )

            save_message(
                saved_conversation,
                "assistant",
                full_reply
            )

            db.session.commit()

            yield (
                "event: done\n"
                f"data: {json.dumps({'success': True, 'conversation_id': conversation_id})}\n\n"
            )

        except GeneratorExit:

            db.session.rollback()
            raise

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Streaming response failed."
            )

            yield (
                "event: error\n"
                f"data: {json.dumps({'error': 'Autoflick AI could not complete the response.'})}\n\n"
            )

        finally:
            db.session.remove()

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


# ==================================================
# PDF DOCUMENT ANALYSIS
# ==================================================

@chat_bp.route(
    "/api/analyze-document",
    methods=["POST"]
)
def analyze_document():

    uploaded_file = request.files.get("file")

    question = request.form.get(
        "question", ""
    ).strip()

    conversation_id = request.form.get(
        "conversation_id"
    )

    if not uploaded_file:
        return jsonify({
            "success": False,
            "error": "Please upload a PDF document."
        }), 400

    filename = uploaded_file.filename or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        return jsonify({
            "success": False,
            "error": "Only PDF documents are supported."
        }), 400

    file_bytes = uploaded_file.read()

    if not file_bytes:
        return jsonify({
            "success": False,
            "error": "The uploaded PDF is empty."
        }), 400

    if len(file_bytes) > MAX_FILE_SIZE:
        return jsonify({
            "success": False,
            "error": "The PDF must be smaller than 10 MB."
        }), 400

    if not file_bytes.startswith(b"%PDF"):
        return jsonify({
            "success": False,
            "error": "The uploaded file is not a valid PDF."
        }), 400

    try:

        reader = PdfReader(BytesIO(file_bytes))

        if reader.is_encrypted:
            return jsonify({
                "success": False,
                "error": (
                    "Password-protected PDFs are not supported."
                )
            }), 400

        page_count = len(reader.pages)

        if page_count > MAX_PAGES:
            return jsonify({
                "success": False,
                "error": "The PDF cannot exceed 50 pages."
            }), 400

        extracted_text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        ).strip()

        if not extracted_text:
            return jsonify({
                "success": False,
                "error": (
                    "No readable text was found in this PDF. "
                    "Scanned PDFs are not currently supported."
                )
            }), 400

        truncated = (
            len(extracted_text) > MAX_DOCUMENT_CHARS
        )

        document_text = extracted_text[
            :MAX_DOCUMENT_CHARS
        ]

        user_prompt = question or (
            "Please analyse this document and provide a "
            "clear summary of its main points."
        )

        client = get_openai_client()

        response = client.chat.completions.create(
            model=get_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Autoflick AI, an assistant that "
                        "analyses PDF documents. Base your answers "
                        "on the supplied document. If the document "
                        "does not contain the requested information, "
                        "state that clearly."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Document name: {filename}\n\n"
                        f"Document content:\n{document_text}\n\n"
                        f"User request: {user_prompt}"
                    )
                }
            ],
            temperature=0.3
        )

        reply = response.choices[0].message.content

        if not reply:
            raise RuntimeError(
                "The AI returned an empty response."
            )

        conversation = get_or_create_conversation(
            conversation_id,
            user_prompt
        )

        save_message(
            conversation,
            "user",
            f"PDF: {filename}\n{user_prompt}"
        )

        save_message(
            conversation,
            "assistant",
            reply
        )

        db.session.commit()

        return jsonify({
            "success": True,
            "reply": reply,
            "filename": filename,
            "pages": page_count,
            "model": get_model(),
            "truncated": truncated,
            "conversation_id": conversation.id
        }), 200

    except (ValueError, LookupError) as error:

        db.session.rollback()

        status_code = (
            404 if isinstance(error, LookupError) else 400
        )

        return jsonify({
            "success": False,
            "error": str(error)
        }), status_code

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "PDF analysis failed."
        )

        return jsonify({
            "success": False,
            "error": (
                "Autoflick AI could not analyse this document."
            )
        }), 500


# ==================================================
# GET ALL CONVERSATIONS
# ==================================================

@chat_bp.route(
    "/api/conversations",
    methods=["GET"]
)
def get_conversations():

    conversations = (
        Conversation.query
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    return jsonify({
        "success": True,
        "conversations": [
            serialize_conversation(item)
            for item in conversations
        ]
    }), 200


# ==================================================
# GET ONE CONVERSATION WITH MESSAGES
# ==================================================

@chat_bp.route(
    "/api/conversations/<int:conversation_id>",
    methods=["GET"]
)
def get_conversation(conversation_id):

    conversation = db.session.get(
        Conversation,
        conversation_id
    )

    if not conversation:
        return jsonify({
            "success": False,
            "error": "Conversation not found."
        }), 404

    return jsonify({
        "success": True,
        "conversation": serialize_conversation(
            conversation
        ),
        "messages": [
            serialize_message(item)
            for item in conversation.messages
        ]
    }), 200


# ==================================================
# DELETE CONVERSATION
# ==================================================

@chat_bp.route(
    "/api/conversations/<int:conversation_id>",
    methods=["DELETE"]
)
def delete_conversation(conversation_id):

    conversation = db.session.get(
        Conversation,
        conversation_id
    )

    if not conversation:
        return jsonify({
            "success": False,
            "error": "Conversation not found."
        }), 404

    try:

        db.session.delete(conversation)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Conversation deleted successfully."
        }), 200

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Conversation deletion failed."
        )

        return jsonify({
            "success": False,
            "error": (
                "Unable to delete this conversation."
            )
        }), 500
