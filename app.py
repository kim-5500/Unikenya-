import os
import re
import html as htmlmod
import base64
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(
    title="UNIKENYA Backend",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

TIMEOUT = 15
UA = "UNIKENYA/1.0"


# ============================================================
# KIM - GEMINI
# ============================================================

class KimRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/kim")
def kim(req: KimRequest):

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise HTTPException(
            503,
            "GEMINI_API_KEY is not configured on the server"
        )

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.1-flash-lite"
    )

    system_instruction = """
You are Kim, the general AI assistant inside UNIKENYA,
a Kenyan citizen super-platform.

Be helpful with:
- general questions
- coding
- mathematics
- writing
- science
- education
- careers
- business
- planning
- research
- technology
- everyday questions
- Kenyan information

For Kenya-specific government services:
- Prefer official Kenyan sources when known.
- Never claim access to private citizen records.
- Never ask for passwords.
- Never ask for M-PESA PINs.
- Never ask for OTPs.
- Never claim a transaction is completed unless an
  authorized connected service confirms it.

When information may have changed recently,
tell the user that it should be verified.

Give practical, clear and useful answers.
Keep answers concise unless the user asks for detail.
Do not invent information.
"""

    conversation = system_instruction.strip() + "\n\n"

    for item in req.history[-10:]:

        role = item.get("role")

        content = str(
            item.get("content", "")
        ).strip()

        if not content:
            continue

        if role == "user":

            conversation += (
                "USER:\n"
                + content[:12000]
                + "\n\n"
            )

        elif role == "assistant":

            conversation += (
                "KIM:\n"
                + content[:12000]
                + "\n\n"
            )

    conversation += (
        "USER:\n"
        + req.message[:12000]
    )

    try:

        url = (
            "https://generativelanguage.googleapis.com"
            "/v1beta/interactions"
        )

        payload = {
            "model": model,
            "input": conversation,
            "store": False
        }

        response = requests.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code >= 400:

            error = data.get(
                "error",
                {}
            )

            message = (
                error.get("message")
                or data.get("message")
                or "Gemini request failed"
            )

            raise HTTPException(
                response.status_code,
                message
            )

        answer = str(
            data.get(
                "output_text",
                ""
            )
        ).strip()

        if not answer:

            steps = data.get(
                "steps",
                []
            )

            collected = []

            for step in steps:

                if step.get(
                    "type"
                ) != "model_output":
                    continue

                content = step.get(
                    "content",
                    []
                )

                if isinstance(
                    content,
                    str
                ):

                    collected.append(
                        content
                    )

                elif isinstance(
                    content,
                    list
                ):

                    for part in content:

                        if isinstance(
                            part,
                            dict
                        ):

                            text = part.get(
                                "text",
                                ""
                            )

                            if text:
                                collected.append(
                                    str(text)
                                )

            answer = "".join(
                collected
            ).strip()

        if not answer:

            raise HTTPException(
                502,
                "Gemini returned an empty answer"
            )

        return {
            "answer": answer,
            "model": model
        }

    except HTTPException:
        raise

    except requests.Timeout:

        raise HTTPException(
            504,
            "Kim took too long to respond. Please try again."
        )

    except requests.RequestException:

        raise HTTPException(
            502,
            "Unable to connect to Gemini."
        )

    except Exception as e:

        raise HTTPException(
            502,
            "Kim backend error: "
            + type(e).__name__
        )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "service": "UNIKENYA backend",
        "time": datetime.now(
            timezone.utc
        ).isoformat()
    }


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):

    value = re.sub(
        r"<[^>]+>",
        " ",
        value or ""
    )

    value = htmlmod.unescape(
        value
    )

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def rss_items(
    feed,
    source,
    category
):

    response = requests.get(
        feed,
        headers={
            "User-Agent": UA
        },
        timeout=TIMEOUT
    )

    response.raise_for_status()

    root = ET.fromstring(
        response.content
    )

    output = []

    for item in root.findall(
        ".//item"
    )[:12]:

        title = clean_text(
            item.findtext("title")
        )

        link = clean_text(
            item.findtext("link")
        )

        description = clean_text(
            item.findtext("description")
        )[:240]

        published = clean_text(
            item.findtext("pubDate")
        )

        if title and link:

            output.append({
                "title": title,
                "url": link,
                "summary": description,
                "source": source,
                "category": category,
                "published": published
            })

    return output


# ============================================================
# M-PESA
# ============================================================

class MpesaRequest(BaseModel):

    phone: str
    amount: int
    reference: str = "UNIKENYA"
    description: str = "UNIKENYA purchase"


def mpesa_base():

    environment = os.getenv(
        "MPESA_ENV",
        "sandbox"
    ).lower()

    if environment in (
        "production",
        "live"
    ):

        return "https://api.safaricom.co.ke"

    return "https://sandbox.safaricom.co.ke"


def mpesa_token():

    key = os.getenv(
        "MPESA_CONSUMER_KEY"
    )

    secret = os.getenv(
        "MPESA_CONSUMER_SECRET"
    )

    if not key or not secret:

        raise HTTPException(
            503,
            "Safaricom Daraja credentials are not configured on the server"
        )

    credentials = base64.b64encode(
        f"{key}:{secret}".encode()
    ).decode()

    response = requests.get(
        mpesa_base()
        + "/oauth/v1/generate"
        + "?grant_type=client_credentials",

        headers={
            "Authorization":
                "Basic " + credentials
       
