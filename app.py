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


# ============================================================
# UNIKENYA BACKEND
# ============================================================

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

You are helpful across:

- General questions
- Coding
- Mathematics
- Writing
- Science
- Education
- Careers
- Business
- Planning
- Research
- Technology
- Everyday questions
- Kenyan information

For Kenya-specific government services:

- Prefer official Kenyan sources when known.
- Never claim access to private citizen records.
- Never ask for passwords.
- Never ask for M-PESA PINs.
- Never ask for OTPs.
- Never pretend to have completed a government transaction
  unless the connected service actually confirms it.

When information may have changed recently,
tell the user that it should be verified.

Give practical, clear and useful answers.

Keep answers concise unless the user asks for detail.

If the user asks something you cannot know,
say so instead of inventing information.

You are Kim, the AI assistant of UNIKENYA.
"""


    try:

        # ----------------------------------------------------
        # BUILD CONVERSATION
        # ----------------------------------------------------

        conversation = (
            system_instruction.strip()
            + "\n\n"
        )

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


        # ----------------------------------------------------
        # GEMINI INTERACTIONS API
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # READ RESPONSE
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # NORMAL OUTPUT
        # ----------------------------------------------------

        answer = str(
            data.get(
                "output_text",
                ""
            )
        ).strip()


        # ----------------------------------------------------
        # FALLBACK OUTPUT PARSER
        # ----------------------------------------------------

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

                        if not isinstance(
                            part,
                            dict
                        ):
                            continue

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
# HEALTH CHECK
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
            item.findtext(
                "description"
            )
        )[:240]

        published = clean_text(
            item.findtext(
                "pubDate"
            )
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

        return (
            "https://api.safaricom.co.ke"
        )

    return (
        "https://sandbox.safaricom.co.ke"
    )


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
        },

        timeout=TIMEOUT
    )

    response.raise_for_status()

    return response.json()[
        "access_token"
    ]


@app.post("/api/mpesa/stkpush")
def mpesa_stkpush(
    req: MpesaRequest
):

    phone = re.sub(
        r"\D",
        "",
        req.phone
    )

    if phone.startswith("0"):

        phone = (
            "254"
            + phone[1:]
        )

    if phone.startswith("+"):

        phone = phone[1:]


    if not re.fullmatch(
        r"2547\d{8}",
        phone
    ):

        raise HTTPException(
            400,
            "Use a valid Kenyan Safaricom number, e.g. 0712345678"
        )


    if (
        req.amount < 1
        or req.amount > 150000
    ):

        raise HTTPException(
            400,
            "Amount must be between KSh 1 and KSh 150,000"
        )


    shortcode = os.getenv(
        "MPESA_SHORTCODE"
    )

    passkey = os.getenv(
        "MPESA_PASSKEY"
    )

    callback = os.getenv(
        "MPESA_CALLBACK_URL"
    )


    if (
        not shortcode
        or not passkey
        or not callback
    ):

        raise HTTPException(
            503,
            "Safaricom STK configuration is incomplete on the server"
        )


    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )


    password = base64.b64encode(
        (
            shortcode
            + passkey
            + timestamp
        ).encode()
    ).decode()


    payload = {

        "BusinessShortCode":
            shortcode,

        "Password":
            password,

        "Timestamp":
            timestamp,

        "TransactionType":
            "CustomerPayBillOnline",

        "Amount":
            req.amount,

        "PartyA":
            phone,

        "PartyB":
            shortcode,

        "PhoneNumber":
            phone,

        "CallBackURL":
            callback,

        "AccountReference":
            re.sub(
                r"[^A-Za-z0-9 ]",
                "",
                req.reference
            )[:12]
            or "UNIKENYA",

        "TransactionDesc":
            re.sub(
                r"[^A-Za-z0-9 ]",
                "",
                req.description
            )[:13]
            or "UNIKENYA"
    }


    try:

        token = mpesa_token()

        response = requests.post(

            mpesa_base()
            + "/mpesa/stkpush/v1/processrequest",

            json=payload,

            headers={

                "Authorization":
                    "Bearer " + token,

                "Content-Type":
                    "application/json"
            },

            timeout=TIMEOUT
        )


        try:

            data = response.json()

        except Exception:

            data = {}


        if response.status_code >= 400:

            raise HTTPException(

                response.status_code,

                data.get(
                    "errorMessage"
                )
                or data.get(
                    "errorCode"
                )
                or "Safaricom rejected the request"
            )


        return data


    except HTTPException:

        raise


    except Exception as e:

        raise HTTPException(

            502,

            "Safaricom payment request failed: "
            + type(e).__name__
        )


@app.post("/api/mpesa/callback")
def mpesa_callback(
    payload: dict
):

    return {

        "ResultCode":
            0,

        "ResultDesc":
            "Accepted"
    }


# ============================================================
# NEWS
# ============================================================

@app.get("/api/news")
def news():

    feeds = [

        (
            "https://www.standardmedia.co.ke/rssfeeds",
            "The Standard",
            "National"
        ),

        (
            "https://www.the-star.co.ke/rss",
            "The Star",
            "National"
        ),

        (
            "https://www.businessdailyafrica.com/rss",
            "Business Daily",
            "Business"
        ),

        (
            "https://nation.africa/kenya/rss",
            "Daily Nation",
            "National"
        )
    ]


    items = []


    for feed, source, category in feeds:

        try:

            items.extend(
                rss_items(
                    feed,
                    source,
                    category
                )
            )

        except Exception:

            pass


    if not items:

        raise HTTPException(
            503,
            "News feeds temporarily unavailable"
        )


    return {

        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "items":
            items[:40]
    }


# ============================================================
# MARKETS
# ============================================================

def parse_table_rows(
    page,
    max_rows=30
):

    from html.parser import HTMLParser


    class Parser(
        HTMLParser
    ):

        def __init__(self):

            super().__init__()

            self.in_td = False

            self.row = []

            self.rows = []

            self.buffer = ""


        def handle_starttag(
            self,
            tag,
            attrs
        ):

            if tag in (
                "td",
                "th"
            ):

                self.in_td = True

                self.buffer = ""


            elif tag == "tr":

                self.row = []


        def handle_data(
            self,
            data
        ):

            if self.in_td:

                self.buffer += (
                    data + " "
                )


        def handle_endtag(
            self,
            tag
        ):

            if (
                tag in (
                    "td",
                    "th"
                )
                and self.in_td
            ):

                self.row.append(
                    clean_text(
                        self.buffer
                    )
                )

                self.in_td = False


            elif (
                tag == "tr"
                and self.row
            ):

                if any(
                    self.row
                ):

                    self.rows.append(
                        self.row[:]
                    )


    parser = Parser()

    parser.feed(page)

    return parser.rows[:max_rows]


@app.get("/api/markets")
def markets(

    kind: str | None = None,

    county: str | None = None,

    market: str | None = None,

    commodity: str | None = None
):

    sections = []


    # --------------------------------------------------------
    # CBK FOREX
    # --------------------------------------------------------

    try:

        page = requests.get(

            "https://www.centralbank.go.ke/forex/",

            headers={
                "User-Agent": UA
            },

            timeout=TIMEOUT
        ).text


        text = clean_text(
            page
        )


        rates = []


        for code, label in [

            ("USD", "US DOLLAR"),

            ("GBP", "STG POUND"),

            ("EUR", "EURO")
        ]:

            match = re.search(

                rf"{code}[^0-9]{{0,80}}([0-9]+\.[0-9]+)",

                text,

                re.I
            )


            if match:

                rates.append([

                    label,

                    match.group(1),

                    "KES"
                ])


        if rates:

            sections.append({

                "title":
                    "Forex",

                "source":
                    "Central Bank of Kenya",

               
