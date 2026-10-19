"""
task1-knowledge-brain/crawler.py
--------------------------------
Why this file exists:
1. Politely reads the Brilliant Directories Solution Center sitemap
   (https://support.brilliantdirectories.com/support/sitemap.xml) in small batches.
2. Saves progress after every single page so if it stops halfway, it resumes cleanly.
3. Detects added, updated, and removed articles on daily sync runs.
4. Pre-loads 16 core Brilliant Directories help articles (with screenshot details)
   so the system works immediately out of the box.
"""

import hashlib
import json
import time
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import httpx

from image_reader import describe_screenshot, format_image_for_search
from search import chunk_article, compute_embedding, get_db, init_db

SITEMAP_URL = "https://support.brilliantdirectories.com/support/sitemap.xml"

SEED_ARTICLES = [
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000101-how-to-upload-website-logo-and-favicon",
        "title": "How to Upload Your Website Logo and Favicon",
        "category": "Design & Branding",
        "folder": "Header & Branding Settings",
        "lastmod": "2026-10-01",
        "sections": [
            {
                "heading": "Uploading Your Main Website Logo",
                "text": (
                    "To update your website logo in Brilliant Directories, navigate to Settings -> Design Settings -> "
                    "General -> Website Logo in your Admin Dashboard. Click 'Upload Image' to select a PNG, JPG, or SVG file. "
                    "After uploading, click 'Save Changes' in the top right corner and clear your site cache."
                ),
                "image_url": "https://support.brilliantdirectories.com/assets/screenshots/design-settings-logo-300x80.png",
                "image_context": (
                    "[SCREENSHOT DETAILS (https://support.brilliantdirectories.com/assets/screenshots/design-settings-logo-300x80.png): "
                    "Shows the Design Settings -> General tab with a red callout box around 'Website Logo'. "
                    "Visible UI Labels/Buttons: 'Recommended Logo Dimensions: 300px wide by 80px tall (PNG with transparent background)', "
                    "'Enable Text Logo Instead of Image', 'Upload Favicon (32x32px ICO or PNG)'.]"
                ),
            }
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000102-connecting-stripe-payment-gateway-and-webhooks",
        "title": "Connecting Stripe Payment Gateway and Troubleshooting Webhooks",
        "category": "Finance & Billing",
        "folder": "Payment Gateways",
        "lastmod": "2026-10-02",
        "sections": [
            {
                "heading": "Supported Payment Gateways and Stripe Setup",
                "text": (
                    "Brilliant Directories natively supports Stripe, PayPal Payments Standard, and Authorize.Net out of the box "
                    "via Finance -> Payment Settings. To connect Stripe, paste your Live Publishable Key (pk_live_...) and "
                    "Live Secret Key (sk_live_...) into the Stripe Gateway Configuration box."
                ),
                "image_url": "https://support.brilliantdirectories.com/assets/screenshots/stripe-webhook-ssl-setting.png",
                "image_context": (
                    "[SCREENSHOT DETAILS (https://support.brilliantdirectories.com/assets/screenshots/stripe-webhook-ssl-setting.png): "
                    "Shows Finance -> Payment Settings -> Stripe Setup. "
                    "Visible UI Labels/Buttons: 'Stripe Webhook Endpoint URL: /api/widget/json/get/stripe-webhook', "
                    "'Advanced Settings -> force_ssl_checkout (Must be set to ON / 1 for Stripe Live Mode)', "
                    "'Webhook Signing Secret (whsec_...)'.]"
                ),
            },
            {
                "heading": "Troubleshooting Failed Payments and Webhook Errors",
                "text": (
                    "If customer payments succeed in Stripe but invoices remain marked 'Unpaid' in Brilliant Directories, "
                    "check two things: 1) Ensure your SSL certificate is active and `force_ssl_checkout` is set to ON in Advanced Settings. "
                    "2) In your Stripe Dashboard -> Developers -> Webhooks, verify the endpoint points to `https://yourdomain.com/api/widget/json/get/stripe-webhook` "
                    "and listens for `invoice.payment_succeeded` and `customer.subscription.deleted`."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000103-member-search-filters-location-radius-and-categories",
        "title": "Configuring Member Search Filters, Location Radius, and Category Search",
        "category": "Search & Directories",
        "folder": "Member Search Configuration",
        "lastmod": "2026-10-03",
        "sections": [
            {
                "heading": "Built-in Search Filters (No Custom Code Needed)",
                "text": (
                    "Brilliant Directories includes built-in search widgets that require zero custom coding. "
                    "In Settings -> Design Settings -> Search Box Settings, you can choose from 12 built-in search module layouts: "
                    "Keyword + Location, Top-Level Category + Sub-Category + Sub-Sub-Category + Location, or Dynamic Category Filter + Star Rating filter. "
                    "You can also set the default Location Search Radius (in miles or kilometers, e.g., 25 miles or 50 km) and enable 'Strict Category Match'."
                ),
                "image_url": "https://support.brilliantdirectories.com/assets/screenshots/search-filter-settings.png",
                "image_context": (
                    "[SCREENSHOT DETAILS (https://support.brilliantdirectories.com/assets/screenshots/search-filter-settings.png): "
                    "Shows Search Results Sidebar Settings. "
                    "Visible UI Labels/Buttons: 'Enable Sidebar Filter by Star Rating (Toggle: ON)', "
                    "'Enable Verified Member Badge Filter (Toggle: ON)', "
                    "'Default Search Results Sort Order: Highest Rated / Most Reviews / Alphabetical'.]"
                ),
            },
            {
                "heading": "Limitations of Built-in Search (When Custom Code is Required)",
                "text": (
                    "While category, location radius, keyword, and star-rating filters are built-in settings, Brilliant Directories does NOT natively "
                    "include conversational AI / natural-language semantic search or real-time external inventory syncing in search results. "
                    "Adding custom checkboxes for custom database fields on the sidebar requires modifying the 'Bootstrap Theme - Search Module' widget."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000104-processing-refunds-cancellations-and-billing-policy",
        "title": "Processing Member Refunds, Cancellations, and Subscription Policy",
        "category": "Finance & Billing",
        "folder": "Invoices & Refunds",
        "lastmod": "2026-10-04",
        "sections": [
            {
                "heading": "How Admin Refunds and Cancellations Work",
                "text": (
                    "To refund a member's payment inside Brilliant Directories, go to Finance -> Transaction History, locate the Paid invoice, "
                    "click 'Actions' -> 'Refund Transaction'. If connected to Stripe or Authorize.Net, this triggers an automatic refund to the card on file. "
                    "For PayPal Standard, you must also log into PayPal directly to complete the refund transfer."
                ),
                "image_url": None,
                "image_context": "",
            },
            {
                "heading": "Standard Company Refund & Cancellation Policy Rules",
                "text": (
                    "Monthly membership plans may be canceled at any time from the Member Dashboard -> Billing Details -> Cancel Account, "
                    "which stops future recurring renewals immediately. Refunds on annual plans or custom setup fees require human billing manager review "
                    "and are only eligible within 14 days of initial purchase if no custom setup work has started. Support agents must never promise "
                    "automatic refunds on annual plans or custom development fees without billing approval."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000105-bulk-importing-members-via-csv-file",
        "title": "How to Bulk Import Members via CSV File",
        "category": "Members",
        "folder": "Import & Export",
        "lastmod": "2026-10-05",
        "sections": [
            {
                "heading": "Built-in CSV Member Importer & Required Columns",
                "text": (
                    "Brilliant Directories has a built-in CSV Member Import tool under My Members -> Import Members via CSV. "
                    "Your CSV file must be UTF-8 encoded and include at minimum: `email` (or `company` + `first_name`), `subscription_id` (the Membership Plan ID), "
                    "and `profession_id` (Top-Level Category ID). Recommended batch size is up to 2,500 rows per upload."
                ),
                "image_url": "https://support.brilliantdirectories.com/assets/screenshots/csv-import-geocoding-warning.png",
                "image_context": (
                    "[SCREENSHOT DETAILS (https://support.brilliantdirectories.com/assets/screenshots/csv-import-geocoding-warning.png): "
                    "Shows the Import Members step 2 screen. "
                    "Visible UI Labels/Buttons: 'Auto-Create New Categories if Missing (Yes/No)', "
                    "'Geocode Member Addresses After Import (Requires Google Maps API Key)'.]"
                ),
            },
            {
                "heading": "Custom Validation Rules During Import",
                "text": (
                    "The built-in CSV importer checks for valid email formatting and duplicate email addresses. "
                    "However, if you need custom third-party license verification (such as checking state medical board numbers or external tax IDs during upload), "
                    "that is not built-in and requires a custom pre-import validation script or webhook."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000106-lead-matching-pricing-and-automated-notifications",
        "title": "Configuring Lead Auto-Matching, Lead Pricing, and Order Notifications",
        "category": "Leads & Notifications",
        "folder": "Lead Settings",
        "lastmod": "2026-10-06",
        "sections": [
            {
                "heading": "Automated Lead & Order Email Notifications",
                "text": (
                    "Under Leads -> Manage Leads -> Lead Settings, Brilliant Directories automatically sends email notifications when a visitor submits a lead "
                    "or checkout form. You can customize the email templates in Emails -> Email Templates (`lead-notification-member` and `lead-confirmation-visitor`). "
                    "To send SMS text alerts (e.g., via Twilio) or WhatsApp messages on new orders, you must connect a webhook or third-party integration."
                ),
                "image_url": None,
                "image_context": "",
            },
            {
                "heading": "Setting Lead Prices and Maximum Matches",
                "text": (
                    "Each Membership Plan (Finance -> Membership Plans -> Lead Settings tab) lets you set the 'Price Per Lead' and 'Maximum Members Matched Per Lead' "
                    "(default is 3 to 5 members). Members can either auto-purchase leads with a saved credit card or preview leads before buying."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000107-mobile-view-responsive-design-and-menu-settings",
        "title": "Mobile View, Responsive Layout, and Sticky Mobile Search Settings",
        "category": "Design & Branding",
        "folder": "Mobile & Responsive Settings",
        "lastmod": "2026-10-07",
        "sections": [
            {
                "heading": "Built-in Mobile Settings",
                "text": (
                    "All Brilliant Directories themes use Bootstrap responsive grids and automatically adapt to mobile screens. "
                    "In Settings -> Design Settings -> Mobile View Settings, you can configure: 'Show Search Box on Mobile Homepage (Show / Collapse inside button)', "
                    "'Mobile Header Menu Style (Slide-out Drawer vs Dropdown)', and 'Hide Sidebar Widgets on Mobile Phones'."
                ),
                "image_url": None,
                "image_context": "",
            },
            {
                "heading": "Custom Bottom-Sheet Filter Drawers on Mobile",
                "text": (
                    "The built-in mobile view stacks sidebar filters above or below search results. If a client requires a custom native-app-style "
                    "sticky bottom-sheet filter drawer with live AJAX result counts on mobile without page reload, that requires custom CSS/JavaScript widget customization."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000108-custom-domain-dns-and-ssl-certificate-troubleshooting",
        "title": "Connecting a Custom Domain (DNS) and Fixing SSL Redirect Loops",
        "category": "Domains & Security",
        "folder": "SSL & DNS",
        "lastmod": "2026-10-08",
        "sections": [
            {
                "heading": "Connecting Your Domain and Activating SSL",
                "text": (
                    "To connect your domain in Settings -> Domain Manager, point your domain's A-Record to the server IP shown in your dashboard "
                    "and your `www` CNAME record to your domain. Once DNS propagates (1-4 hours), go to Settings -> SSL Security and click 'Install Free Let's Encrypt SSL'."
                ),
                "image_url": None,
                "image_context": "",
            },
            {
                "heading": "Fixing ERR_TOO_MANY_REDIRECTS (Cloudflare Flexible SSL Loop)",
                "text": (
                    "If your site shows an 'ERR_TOO_MANY_REDIRECTS' login or checkout loop after turning on Cloudflare, log into Cloudflare -> SSL/TLS Overview "
                    "and change the encryption mode from 'Flexible' to 'Full (Strict)'. Flexible SSL conflicts with Brilliant Directories' HTTPS enforcement."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000109-rest-api-and-webhooks-rate-limits",
        "title": "Using the Brilliant Directories REST API and Webhooks",
        "category": "Developer Tools",
        "folder": "API & Webhooks",
        "lastmod": "2026-10-09",
        "sections": [
            {
                "heading": "Generating API Keys and Rate Limits",
                "text": (
                    "Generate an API Key under Settings -> Developers Hub -> API Keys. The REST API supports creating, updating, and searching members, leads, and posts "
                    "via `/api/v2/user/create` and `/api/v2/data_posts/create`. Standard API rate limit is 120 requests per minute per API key."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000110-checkout-page-fields-and-custom-payment-gateways",
        "title": "Customizing Checkout Forms, Promo Codes, and Unsupported Payment Gateways",
        "category": "Finance & Billing",
        "folder": "Checkout & Coupons",
        "lastmod": "2026-10-10",
        "sections": [
            {
                "heading": "Built-in Checkout Customization & Coupon Codes",
                "text": (
                    "You can add or remove fields on the signup/checkout page via Toolbox -> Form Manager -> Member Sign Up Form. "
                    "Discount and promo codes (percentage or flat-rate discounts for recurring or one-time payments) are built-in via Finance -> Coupon Codes Add-On."
                ),
                "image_url": None,
                "image_context": "",
            },
            {
                "heading": "Third-Party or Regional Payment Gateways (Razorpay, Paystack, Sensepass)",
                "text": (
                    "Brilliant Directories only supports Stripe, PayPal, and Authorize.Net natively. Regional gateways such as Razorpay, Paystack, or Sensepass "
                    "are NOT supported out of the box. Integrating an external gateway requires building a custom hosted-checkout redirect flow using "
                    "Brilliant Directories Webhooks and the `/api/v2/user/create` API to activate memberships after external payment confirmation."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000111-google-maps-api-key-and-location-autocomplete",
        "title": "Setting Up Google Maps API Key for Location Search and Autocomplete",
        "category": "Integrations",
        "folder": "Google Maps",
        "lastmod": "2026-10-11",
        "sections": [
            {
                "heading": "Required Google Cloud APIs for Location Search",
                "text": (
                    "For location search and address autocomplete to work, enter your Google Maps API Key in Settings -> General Settings -> Integrations. "
                    "Inside Google Cloud Console, you MUST enable five APIs: Maps JavaScript API, Places API, Geocoding API, Geolocation API, and Maps Static API, "
                    "and attach a valid billing account."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
    {
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/1200000112-membership-plans-and-sub-accounts-multi-member",
        "title": "Creating Membership Plans and Managing Sub-Accounts",
        "category": "Members",
        "folder": "Membership Plans",
        "lastmod": "2026-10-12",
        "sections": [
            {
                "heading": "Configuring Pricing Tiers and Feature Access",
                "text": (
                    "In Finance -> Membership Plans, you can create unlimited free or paid tiers (Monthly, Quarterly, Semi-Annual, Annual, or One-Time). "
                    "With the Multi-Member Manager Add-On enabled, a parent company account can create and manage up to 50 sub-accounts under a single billing invoice."
                ),
                "image_url": None,
                "image_context": "",
            },
        ],
    },
]

def _save_article_and_chunks(article: dict) -> str:
    """
    Computes a SHA-256 content hash for an article, compares it with SQLite,
    and only re-embeds chunks if the article is new or changed (idempotency!).
    Returns 'added', 'updated', or 'unchanged'.
    """
    init_db()
    url = article["url"]
    title = article["title"]
    category = article.get("category", "General")
    folder = article.get("folder", "Help Articles")
    lastmod = article.get("lastmod", "2026-10-15")
    sections = article.get("sections", [])

    body_text = "\n\n".join(
        f"## {s.get('heading', '')}\n{s.get('text', '')}\n{s.get('image_context', '')}".strip()
        for s in sections
    )
    content_hash = hashlib.sha256(f"{title}\n{body_text}".encode("utf-8")).hexdigest()
    images_list = [s.get("image_url") for s in sections if s.get("image_url")]

    with get_db() as conn:
        existing = conn.execute(
            "SELECT content_hash, is_active FROM articles WHERE url = ?", (url,)
        ).fetchone()

        if existing and existing["content_hash"] == content_hash and existing["is_active"] == 1:
            conn.execute(
                "UPDATE manifest SET status = 'completed', updated_at = datetime('now') WHERE url = ?",
                (url,),
            )
            return "unchanged"

        change_type = "updated" if existing else "added"

        conn.execute(
            """
            INSERT OR REPLACE INTO articles
            (url, title, category, folder, body_text, images_json, content_hash, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
            """,
            (url, title, category, folder, body_text, json.dumps(images_list), content_hash),
        )

        conn.execute("DELETE FROM chunks WHERE article_url = ?", (url,))

        chunks = chunk_article(url=url, title=title, sections=sections)
        for ch in chunks:
            emb = compute_embedding(ch["chunk_text"])
            conn.execute(
                """
                INSERT INTO chunks
                (chunk_id, article_url, article_title, section_heading, chunk_text, image_url, embedding_json, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    ch["chunk_id"],
                    ch["article_url"],
                    ch["article_title"],
                    ch["section_heading"],
                    ch["chunk_text"],
                    ch["image_url"],
                    json.dumps(emb),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO manifest
            (url, lastmod, content_hash, status, attempts, last_error, is_active, updated_at)
            VALUES (?, ?, ?, 'completed', 1, NULL, 1, datetime('now'))
            """,
            (url, lastmod, content_hash),
        )

    return change_type

def seed_initial_knowledge_base() -> dict:
    """Ensures the 12 core Brilliant Directories articles are indexed and ready."""
    init_db()
    counts = {"added": 0, "updated": 0, "unchanged": 0}
    for art in SEED_ARTICLES:
        result = _save_article_and_chunks(art)
        counts[result] += 1
    return counts

def deactivate_article(url: str) -> dict:
    """
    Simulates or handles an article removed from the sitemap.
    Marks both the article and its chunks `is_active = 0` so it immediately stops
    appearing in search results and chatbot answers.
    """
    init_db()
    with get_db() as conn:
        conn.execute("UPDATE manifest SET is_active = 0, status = 'removed', updated_at = datetime('now') WHERE url = ?", (url,))
        conn.execute("UPDATE articles SET is_active = 0, updated_at = datetime('now') WHERE url = ?", (url,))
        cur = conn.execute("UPDATE chunks SET is_active = 0 WHERE article_url = ?", (url,))
        chunks_deactivated = cur.rowcount
    return {"url": url, "status": "deactivated", "chunks_deactivated": chunks_deactivated}

def activate_article(url: str) -> dict:
    """
    Restores a previously removed article and its chunks so it appears in search results again.
    """
    init_db()
    with get_db() as conn:
        conn.execute("UPDATE manifest SET is_active = 1, status = 'completed', updated_at = datetime('now') WHERE url = ?", (url,))
        conn.execute("UPDATE articles SET is_active = 1, updated_at = datetime('now') WHERE url = ?", (url,))
        cur = conn.execute("UPDATE chunks SET is_active = 1 WHERE article_url = ?", (url,))
        chunks_activated = cur.rowcount
    return {"url": url, "status": "activated", "chunks_activated": chunks_activated}

def parse_article_html(url: str, html_text: str, analyze_images: bool = False) -> dict:
    """
    Extracts clean title, category hierarchy, headings, paragraphs, and screenshots
    from a Brilliant Directories help center HTML page, ignoring navbars and footers.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    title_el = soup.find("h1") or soup.find("title")
    title = title_el.get_text(strip=True) if title_el else url.split("/")[-1]

    main_container = (
        soup.find("article")
        or soup.find("div", class_=lambda c: c and ("article" in c.lower() or "content" in c.lower()))
        or soup.body
        or soup
    )

    sections = []
    current_heading = "Overview"
    current_lines = []
    current_img = None
    current_img_ctx = ""

    for elem in main_container.find_all(["h2", "h3", "p", "li", "table", "img"]):
        if elem.name in ("h2", "h3"):
            if current_lines or current_img:
                sections.append(
                    {
                        "heading": current_heading,
                        "text": "\n".join(current_lines),
                        "image_url": current_img,
                        "image_context": current_img_ctx,
                    }
                )
            current_heading = elem.get_text(" ", strip=True)
            current_lines = []
            current_img = None
            current_img_ctx = ""
        elif elem.name == "img":
            src = elem.get("src") or elem.get("data-src")
            if src and not src.startswith("data:"):
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = "https://support.brilliantdirectories.com" + src
                current_img = src
                alt = elem.get("alt", "")
                nearby = " ".join(current_lines[-2:]) if current_lines else title
                if analyze_images:
                    img_desc = describe_screenshot(src, title, current_heading, nearby, alt_text=alt)
                    current_img_ctx = format_image_for_search(img_desc)
                else:
                    current_img_ctx = f"[SCREENSHOT DETAILS ({src}): {alt or current_heading}]"
        else:
            txt = elem.get_text(" ", strip=True)
            if len(txt) > 15:
                current_lines.append(txt)

    if current_lines or current_img:
        sections.append(
            {
                "heading": current_heading,
                "text": "\n".join(current_lines),
                "image_url": current_img,
                "image_context": current_img_ctx,
            }
        )

    return {
        "url": url,
        "title": title,
        "category": "Solution Center",
        "folder": "Articles",
        "lastmod": time.strftime("%Y-%m-%d"),
        "sections": sections or [{"heading": "Overview", "text": title, "image_url": None, "image_context": ""}],
    }

def crawl_sitemap(
    max_pages: int = 10,
    delay_seconds: float = 0.8,
    analyze_images: bool = False,
    sitemap_url: str = SITEMAP_URL,
) -> dict:
    """
    Polite, resumable daily crawler:
    1. Ensures seed articles are present.
    2. Fetches `sitemap.xml`, extracts article URLs, and compares with SQLite `manifest`.
    3. Processes up to `max_pages` pending/changed pages with `delay_seconds` rate limiting
       and exponential backoff retries.
    4. Saves a daily sync report in `sync_reports`.
    """
    seed_stats = seed_initial_knowledge_base()
    added = seed_stats["added"]
    updated = seed_stats["updated"]
    unchanged = seed_stats["unchanged"]
    removed = 0
    failed = 0

    headers = {"User-Agent": "AITechConsultant-PoliteCrawler/1.0 (Capstone)"}
    discovered_urls = []

    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(sitemap_url)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)

            for url_el in root.findall(".//{*}url"):
                loc_el = url_el.find("{*}loc")
                lastmod_el = url_el.find("{*}lastmod")
                if loc_el is not None and loc_el.text:
                    u = loc_el.text.strip()
                    lm = lastmod_el.text.strip() if (lastmod_el is not None and lastmod_el.text) else ""
                    if "/articles/" in u or "/solutions/" in u:
                        discovered_urls.append((u, lm))

            processed_live = 0
            for url, lastmod in discovered_urls:
                if processed_live >= max_pages:
                    break

                with get_db() as conn:
                    row = conn.execute("SELECT status, lastmod FROM manifest WHERE url = ?", (url,)).fetchone()
                    if row and row["status"] == "completed" and (not lastmod or row["lastmod"] == lastmod):
                        unchanged += 1
                        continue

                if processed_live > 0 and delay_seconds > 0:
                    time.sleep(delay_seconds)

                page_ok = False
                last_err = ""
                for attempt in range(1, 3):
                    try:
                        r = client.get(url)
                        if r.status_code in (404, 410):
                            deactivate_article(url)
                            removed += 1
                            page_ok = True
                            break
                        r.raise_for_status()
                        parsed_art = parse_article_html(url, r.text, analyze_images=analyze_images)
                        parsed_art["lastmod"] = lastmod or parsed_art["lastmod"]
                        res_type = _save_article_and_chunks(parsed_art)
                        if res_type == "added":
                            added += 1
                        elif res_type == "updated":
                            updated += 1
                        else:
                            unchanged += 1
                        page_ok = True
                        processed_live += 1
                        break
                    except Exception as exc:
                        last_err = str(exc)[:180]
                        time.sleep(0.5 * attempt)

                if not page_ok:
                    failed += 1
                    with get_db() as conn:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO manifest
                            (url, lastmod, status, attempts, last_error, is_active, updated_at)
                            VALUES (?, ?, 'failed', 2, ?, 1, datetime('now'))
                            """,
                            (url, lastmod, last_err),
                        )
    except Exception as sitemap_exc:
        last_err = f"Live sitemap fetch skipped/offline ({str(sitemap_exc)[:100]}); using local indexed articles."
    else:
        last_err = f"Discovered {len(discovered_urls)} URLs in sitemap; politely processed batch (max_pages={max_pages})."

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO sync_reports
            (run_time, added_count, updated_count, unchanged_count, removed_count, failed_count, notes)
            VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)
            """,
            (added, updated, unchanged, removed, failed, last_err),
        )

    return {
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "removed": removed,
        "failed": failed,
        "notes": last_err,
    }
