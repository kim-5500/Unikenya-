import os, re, json, time, html as htmlmod
from datetime import datetime, timezone
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title='UNIKENYA Backend', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*']
)

TIMEOUT = 15
UA = 'UNIKENYA/1.0 (+https://unik-enya.example)'


# ============================================================
# KIM
# ============================================================

class KimRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post('/api/kim')
def kim(req: KimRequest):
    key = os.getenv('GEMINI_API_KEY')

    if not key:
        raise HTTPException(
            503,
            'GEMINI_API_KEY is not configured on the server'
        )

    try:
        model = os.getenv(
            'GEMINI_MODEL',
            'gemini-2.5-flash-lite'
        )

        system = """You are Kim, the general AI assistant inside UNIKENYA, a Kenyan citizen super-platform.

Be helpful across coding, math, writing, science, planning, research, careers and everyday questions.

For Kenya-specific government services, use official sources when known and never claim access to private citizen records.

Never request passwords, PINs or OTPs.

When information may be current, say when it should be verified and prefer official Kenyan sources.

Give practical next steps and concise answers unless the user asks for detail."""

        conversation = []

        for h in req.history[-10:]:
            role = h.get('role')
            content = str(h.get('content', '')).strip()

            if role in ('user', 'assistant') and content:
                conversation.append({
                    'role': 'user' if role == 'user' else 'model',
                    'parts': [{'text': content}]
                })

        conversation.append({
            'role': 'user',
            'parts': [
                {
                    'text': system + '\n\n' + req.message[:12000]
                }
            ]
        })

        url = (
            f'https://generativelanguage.googleapis.com/v1beta/'
            f'models/{model}:generateContent?key={key}'
        )

        payload = {
            'contents': conversation,
            'generationConfig': {
                'temperature': 0.7,
                'maxOutputTokens': 2048
            }
        }

        response = requests.post(
            url,
            json=payload,
            headers={
                'Content-Type': 'application/json'
            },
            timeout=30
        )

        data = response.json()

        if response.status_code >= 400:
            error_message = (
                data.get('error', {}).get('message')
                or 'Gemini rejected the request'
            )
            raise HTTPException(
                response.status_code,
                error_message
            )

        candidates = data.get('candidates', [])

        if not candidates:
            raise HTTPException(
                502,
                'Gemini returned no answer'
            )

        parts = (
            candidates[0]
            .get('content', {})
            .get('parts', [])
        )

        answer = ''.join(
            str(part.get('text', ''))
            for part in parts
            if part.get('text')
        ).strip()

        if not answer:
            raise HTTPException(
                502,
                'Gemini returned an empty answer'
            )

        return {
            'answer': answer,
            'model': model
        }

    except HTTPException:
        raise

    except requests.RequestException:
        raise HTTPException(
            502,
            'Unable to connect to Gemini'
        )

    except Exception as e:
        raise HTTPException(
            502,
            f'Kim backend error: {type(e).__name__}'
        )


# ============================================================
# HEALTH
# ============================================================

@app.get('/health')
def health():
    return {
        'ok': True,
        'service': 'UNIKENYA backend',
        'time': datetime.now(timezone.utc).isoformat()
    }


# ============================================================
# TEXT / NEWS HELPERS
# ============================================================

def clean_text(x):
    x = re.sub(r'<[^>]+>', ' ', x or '')
    x = htmlmod.unescape(x)
    return re.sub(r'\s+', ' ', x).strip()


def rss_items(feed, source, category):
    r = requests.get(
        feed,
        headers={'User-Agent': UA},
        timeout=TIMEOUT
    )

    r.raise_for_status()

    root = ET.fromstring(r.content)

    out = []

    for item in root.findall('.//item')[:12]:
        title = clean_text(item.findtext('title'))
        link = clean_text(item.findtext('link'))
        desc = clean_text(
            item.findtext('description')
        )[:240]
        pub = clean_text(item.findtext('pubDate'))

        if title and link:
            out.append({
                'title': title,
                'url': link,
                'summary': desc,
                'source': source,
                'category': category,
                'published': pub
            })

    return out


# ============================================================
# MPESA
# ============================================================

class MpesaRequest(BaseModel):
    phone: str
    amount: int
    reference: str = 'UNIKENYA'
    description: str = 'UNIKENYA purchase'


def mpesa_base():
    return (
        'https://api.safaricom.co.ke'
        if os.getenv(
            'MPESA_ENV',
            'sandbox'
        ).lower() in ('production', 'live')
        else
        'https://sandbox.safaricom.co.ke'
    )


def mpesa_token():
    import base64

    key = os.getenv('MPESA_CONSUMER_KEY')
    secret = os.getenv('MPESA_CONSUMER_SECRET')

    if not key or not secret:
        raise HTTPException(
            503,
            'Safaricom Daraja credentials are not configured on the server'
        )

    raw = base64.b64encode(
        f'{key}:{secret}'.encode()
    ).decode()

    r = requests.get(
        mpesa_base()
        + '/oauth/v1/generate?grant_type=client_credentials',
        headers={
            'Authorization': 'Basic ' + raw
        },
        timeout=TIMEOUT
    )

    r.raise_for_status()

    return r.json()['access_token']


@app.post('/api/mpesa/stkpush')
def mpesa_stkpush(req: MpesaRequest):
    import base64

    phone = re.sub(r'\D', '', req.phone)

    if phone.startswith('0'):
        phone = '254' + phone[1:]

    if phone.startswith('+'):
        phone = phone[1:]

    if not re.fullmatch(r'2547\d{8}', phone):
        raise HTTPException(
            400,
            'Use a valid Kenyan Safaricom number, e.g. 0712345678'
        )

    if req.amount < 1 or req.amount > 150000:
        raise HTTPException(
            400,
            'Amount must be between KSh 1 and KSh 150,000'
        )

    shortcode = os.getenv('MPESA_SHORTCODE')
    passkey = os.getenv('MPESA_PASSKEY')
    callback = os.getenv('MPESA_CALLBACK_URL')

    if not shortcode or not passkey or not callback:
        raise HTTPException(
            503,
            'Safaricom STK configuration is incomplete on the server'
        )

    timestamp = datetime.now().strftime(
        '%Y%m%d%H%M%S'
    )

    password = base64.b64encode(
        f'{shortcode}{passkey}{timestamp}'.encode()
    ).decode()

    payload = {
        'BusinessShortCode': shortcode,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': req.amount,
        'PartyA': phone,
        'PartyB': shortcode,
        'PhoneNumber': phone,
        'CallBackURL': callback,
        'AccountReference': re.sub(
            r'[^A-Za-z0-9 ]',
            '',
            req.reference
        )[:12] or 'UNIKENYA',
        'TransactionDesc': re.sub(
            r'[^A-Za-z0-9 ]',
            '',
            req.description
        )[:13] or 'UNIKENYA'
    }

    try:
        token = mpesa_token()

        r = requests.post(
            mpesa_base()
            + '/mpesa/stkpush/v1/processrequest',
            json=payload,
            headers={
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            timeout=TIMEOUT
        )

        data = r.json()

        if r.status_code >= 400:
            raise HTTPException(
                r.status_code,
                data.get('errorMessage')
                or data.get('errorCode')
                or 'Safaricom rejected the request'
            )

        return data

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            502,
            f'Safaricom payment request failed: {type(e).__name__}'
        )


@app.post('/api/mpesa/callback')
def mpesa_callback(payload: dict):
    return {
        'ResultCode': 0,
        'ResultDesc': 'Accepted'
    }


# ============================================================
# NEWS
# ============================================================

@app.get('/api/news')
def news():
    feeds = [
        (
            'https://www.standardmedia.co.ke/rssfeeds',
            'The Standard',
            'National'
        ),
        (
            'https://www.the-star.co.ke/rss',
            'The Star',
            'National'
        ),
        (
            'https://www.businessdailyafrica.com/rss',
            'Business Daily',
            'Business'
        ),
        (
            'https://nation.africa/kenya/rss',
            'Daily Nation',
            'National'
        )
    ]

    items = []

    for f, s, c in feeds:
        try:
            items.extend(
                rss_items(f, s, c)
            )
        except Exception:
            pass

    if not items:
        raise HTTPException(
            503,
            'News feeds temporarily unavailable'
        )

    return {
        'updated_at': datetime.now(
            timezone.utc
        ).isoformat(),
        'items': items[:40]
    }


# ============================================================
# MARKETS
# ============================================================

def parse_table_rows(page, max_rows=30):
    from html.parser import HTMLParser

    class P(HTMLParser):

        def __init__(self):
            super().__init__()
            self.in_td = False
            self.row = []
            self.rows = []
            self.buf = ''

        def handle_starttag(self, t, a):
            if t in ('td', 'th'):
                self.in_td = True
                self.buf = ''

            elif t == 'tr':
                self.row = []

        def handle_data(self, d):
            if self.in_td:
                self.buf += d + ' '

        def handle_endtag(self, t):
            if t in ('td', 'th') and self.in_td:
                self.row.append(
                    clean_text(self.buf)
                )
                self.in_td = False

            elif t == 'tr' and self.row:
                if any(self.row):
                    self.rows.append(
                        self.row[:]
                    )

    p = P()
    p.feed(page)

    return p.rows[:max_rows]


@app.get('/api/markets')
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
        t = requests.get(
            'https://www.centralbank.go.ke/forex/',
            headers={'User-Agent': UA},
            timeout=TIMEOUT
        ).text

        txt = clean_text(t)

        rates = []

        for code, label in [
            ('USD', 'US DOLLAR'),
            ('GBP', 'STG POUND'),
            ('EUR', 'EURO')
        ]:
            m = re.search(
                rf'{code}[^0-9]{{0,80}}([0-9]+\.[0-9]+)',
                txt,
                re.I
            )

            if m:
                rates.append([
                    label,
                    m.group(1),
                    'KES'
                ])

        if rates:
            sections.append({
                'title': 'Forex',
                'source': 'Central Bank of Kenya',
                'rows': rates,
                'note': 'Public CBK page; bank transaction rates may differ.'
            })

    except Exception:
        pass

    # --------------------------------------------------------
    # KAMIS
    # --------------------------------------------------------

    try:
        url = 'https://kamis.kilimo.go.ke/site/market'

        page = requests.get(
            url,
            headers={'User-Agent': UA},
            timeout=TIMEOUT
        ).text

        rows = parse_table_rows(page)

        wanted = []

        for row in rows:
            blob = ' '.join(row).lower()

            if county and county.lower() not in blob:
                continue

            if market and market.lower() not in blob:
                continue

            if commodity and commodity.lower() not in blob:
                continue

            wanted.append(row)

        if wanted:
            sections.append({
                'title': 'KAMIS market observations',
                'source': 'Kenya Agricultural Market Information System',
                'rows': wanted[:30],
                'note': 'Public KAMIS observations. Values vary by market/date.'
            })

    except Exception:
        pass

    if not sections:
        raise HTTPException(
            503,
            'Official market sources temporarily unavailable'
        )

    return {
        'updated_at': datetime.now(
            timezone.utc
        ).isoformat(),
        'sections': sections,
        'filters': {
            'kind': kind,
            'county': county,
            'market': market,
            'commodity': commodity
        }
}
