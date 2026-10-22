import json
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings

from .models import Company


def website_logo_url(website):
    """Return a lightweight website icon fallback when no logo is supplied."""
    if not website:
        return ""
    parsed = urlparse(website if "://" in website else f"https://{website}")
    if not parsed.netloc:
        return ""
    return f"https://www.google.com/s2/favicons?domain={quote(parsed.netloc)}&sz=128"


def _linkedin_vanity(value):
    parsed = urlparse(value if "://" in value else f"https://{value}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() == "company":
        return parts[1]
    return value.strip().replace(" ", "-")


def _linkedin_lookup(query):
    token = getattr(settings, "LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        return None

    vanity = _linkedin_vanity(query)
    endpoint = (
        "https://api.linkedin.com/rest/organization"
        f"?q=vanityName&vanityName={quote(vanity)}"
    )
    request = Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Linkedin-Version": getattr(settings, "LINKEDIN_API_VERSION", "202601"),
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    elements = payload.get("elements", [])
    organization = elements[0] if elements else payload
    localized_name = organization.get("localizedName") or organization.get("name", "")
    localized_website = organization.get("localizedWebsite", "")
    organization_id = str(organization.get("id", ""))
    linkedin_url = f"https://www.linkedin.com/company/{organization.get('vanityName', vanity)}/"
    logo_url = _find_image_url(organization.get("logoV2") or organization.get("logo"))
    return {
        "name": localized_name,
        "website": localized_website,
        "linkedin_url": linkedin_url,
        "linkedin_organization_id": organization_id,
        "logo_url": logo_url or website_logo_url(localized_website),
        "source": "linkedin",
    }


def _company_directory_lookup(query):
    """Resolve a company name to a domain when LinkedIn access is unavailable."""
    endpoint = "https://autocomplete.clearbit.com/v1/companies/suggest?query=" + quote(query)
    request = Request(endpoint, headers={"User-Agent": "SkillBridge/1.0"})
    try:
        with urlopen(request, timeout=5) as response:
            results = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    if not isinstance(results, list) or not results:
        return None
    query_lower = query.casefold()
    result = next(
        (item for item in results if str(item.get("name", "")).casefold() == query_lower),
        results[0],
    )
    name = str(result.get("name", "")).strip()
    domain = str(result.get("domain", "")).strip()
    if not name or not domain:
        return None
    website = f"https://{domain}"
    return {
        "name": name,
        "website": website,
        "linkedin_url": "",
        "linkedin_organization_id": "",
        "logo_url": result.get("logo") or website_logo_url(website),
        "source": "company directory",
    }


def _find_image_url(value):
    """Find an image URL in LinkedIn's nested logoV2 response shape."""
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        for child in value.values():
            result = _find_image_url(child)
            if result:
                return result
    if isinstance(value, list):
        for child in value:
            result = _find_image_url(child)
            if result:
                return result
    return ""


def lookup_company(query):
    """Find company data locally, through LinkedIn, or through the directory fallback."""
    query = (query or "").strip()
    if not query:
        return None

    local_company = Company.objects.filter(name__icontains=query).first()
    if local_company:
        return {
            "name": local_company.name,
            "website": local_company.website,
            "industry": local_company.industry,
            "linkedin_url": local_company.linkedin_url,
            "linkedin_organization_id": local_company.linkedin_organization_id,
            "logo_url": local_company.logo_url or website_logo_url(local_company.website),
            "source": "local",
        }

    return _linkedin_lookup(query) or _company_directory_lookup(query)
