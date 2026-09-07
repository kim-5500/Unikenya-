# UNIKENYA — Master Release

This is the consolidated UNIKENYA build: one package containing the citizen web app, PWA shell, Kim backend, public news backend, and market backend.

## Included
- Government service directory and official portal links
- Kim general AI assistant (server-side OpenAI key)
- Kenya maps, directions and nearby-service tools
- Kenya news feed with publisher links
- Markets and price-watch tools with public KAMIS/CBK integrations
- Kenya football and trending/culture discovery
- Jobs, scholarships, education, health/emergency, legal/public-data backends
- Citizen Essentials, budgeting, savings, scam-checking and task planners
- My Kenya Hub and county personalization
- Local-first PWA shell for faster repeat loading

## Run the backend
1. Install Python 3.11+.
2. Create a virtual environment.
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` on the server environment.
5. Run: `uvicorn app:app --host 0.0.0.0 --port 8000`
6. Host `index.html`, `manifest.webmanifest` and `sw.js` from a web server.
7. Set `window.UNIKENYA_API_BASE` in the HTML to the deployed backend URL if the backend is on another domain.

## Important
- Do not put the OpenAI API key inside `index.html` or any client-side JavaScript.
- UNIKENYA links users to official government portals for authenticated/private services; it does not bypass government authentication or access private records without authorization.
- News cards should link to the publisher for the full story rather than copying full articles.
- Public market/news data can be temporarily unavailable; the frontend has dated fallback information where provided.


## New in this release
- Super Tools hub: budget, loan, salary planning, savings goal, rent, investment growth, weather, transport, housing, emergency, farming, documents, price comparison, legal, study, career, civic and Kenya-data assistants.
- Settings screen with persistent dark theme.
- Production calculator with keyboard support, %, brackets, square root and memory; no Function/eval execution.
- `config.js` controls the production backend URL. For same-origin deployment leave it blank; for a separate backend set `window.UNIKENYA_API_BASE` to the HTTPS backend.


### Safaricom in-app checkout
The Safaricom dashboard now opens an in-app checkout sheet when a user taps Buy. It collects only the payment phone number and calls `/api/mpesa/stkpush` so an authorized Daraja STK Push integration can send the M-PESA prompt directly to the phone. Credentials stay server-side. Actual bundle fulfillment must be enabled through the specific Safaricom product/API authorization; an STK payment alone is not a claim that Safaricom has provisioned a data/voice/SMS bundle.
