"""Provider-aware certification verification.

Only an authenticated provider response can complete a milestone. Public links
that cannot be checked through an authorised API are validated and queued for
human review; their HTML is deliberately not scraped.
"""

from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings


@dataclass(frozen=True)
class VerificationResult:
    status: str
    method: str
    message: str


PROVIDER_HOSTS = {
    "coursera": {"coursera.org", "www.coursera.org"},
    "google skillshop": {"skillshop.credential.net", "skillshop.exceedlms.com", "www.credly.com", "credly.com"},
    "google cloud": {"www.credly.com", "credly.com", "credential.net", "www.credential.net"},
    "google cloud skills boost": {"www.credly.com", "credly.com", "cloudskillsboost.google", "www.cloudskillsboost.google"},
    "accredible": {"credential.net", "www.credential.net"},
}


def _provider_key(certification):
    value = certification.provider.casefold().strip()
    if "coursera" in value:
        return "coursera"
    if "skillshop" in value:
        return "google skillshop"
    if "skills boost" in value:
        return "google cloud skills boost"
    if "google cloud" in value:
        return "google cloud"
    if "accredible" in value:
        return "accredible"
    return value


def _host_allowed(host, allowed):
    return any(host == item or host.endswith(f".{item}") for item in allowed)


def _normalise_words(value):
    return set(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _names_match(expected, actual):
    expected_words = _normalise_words(expected) - {"certificate", "certification", "professional", "resources", "learning"}
    actual_words = _normalise_words(actual) - {"certificate", "certification", "professional", "resources", "learning"}
    return bool(expected_words) and len(expected_words & actual_words) >= max(2, len(expected_words) // 2)


def _expected_issuer_brand(certification):
    text = f"{certification.title} {certification.provider}".casefold()
    for brand in ("google cloud", "google", "meta", "aws", "microsoft", "ibm", "harvard"):
        if brand in text:
            return brand
    return ""


def _accredible_id(url):
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    return path_parts[-1] if path_parts else ""


def _verify_accredible(certification, verification_url):
    api_key = getattr(settings, "ACCREDIBLE_API_KEY", "")
    if not api_key:
        return VerificationResult("pending_verification", "accredible_manual", "Accredible link accepted; API access is not configured, so an administrator must review it.")
    credential_id = _accredible_id(verification_url)
    if not credential_id:
        return VerificationResult("rejected", "accredible_api", "The Accredible credential URL does not contain a credential identifier.")
    request = Request(
        f"https://api.accredible.com/v1/credentials/{credential_id}",
        headers={"Authorization": f"Token token={api_key}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return VerificationResult("rejected", "accredible_api", "Accredible could not find this credential.")
        return VerificationResult("pending_verification", "accredible_api", "Accredible could not verify the credential automatically; administrator review is required.")
    except (URLError, TimeoutError, ValueError):
        return VerificationResult("pending_verification", "accredible_api", "The Accredible service is unavailable; administrator review is required.")

    credential = payload.get("credential", payload)
    actual_name = credential.get("name") or credential.get("course_name") or (credential.get("group") or {}).get("course_name", "")
    if not _names_match(certification.title, actual_name):
        return VerificationResult("rejected", "accredible_api", "The credential is valid, but it is for a different certification.")
    issuer = credential.get("issuer") or credential.get("issuer_name") or (credential.get("group") or {}).get("issuer", "")
    if isinstance(issuer, dict):
        issuer = issuer.get("name", "")
    expected_brand = _expected_issuer_brand(certification)
    if expected_brand and expected_brand not in str(issuer).casefold():
        return VerificationResult("rejected", "accredible_api", f"The credential was not issued by the expected organisation: {expected_brand.title()}.")
    if credential.get("expired_on") and credential.get("status") == "expired":
        return VerificationResult("rejected", "accredible_api", "This credential has expired.")
    if credential.get("revoked") is True:
        return VerificationResult("rejected", "accredible_api", "This credential has been revoked.")
    return VerificationResult("completed", "accredible_api", "Verified directly with Accredible and matched to this certification.")


def verify_certificate(certification, verification_url):
    """Validate provider ownership, then use an official API where available."""
    raw_url = (verification_url or "").strip()
    parsed = urlparse(raw_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return VerificationResult("rejected", "url_validation", "Enter the official HTTPS credential URL.")

    provider = _provider_key(certification)
    allowed_hosts = PROVIDER_HOSTS.get(provider)
    if not allowed_hosts:
        return VerificationResult("pending_verification", "manual", "This provider has no supported verification API; administrator review is required.")
    if not _host_allowed(parsed.hostname.casefold(), allowed_hosts):
        return VerificationResult("rejected", "provider_mismatch", f"This link does not belong to the expected provider: {certification.provider}.")

    if parsed.hostname.casefold().endswith("credential.net"):
        return _verify_accredible(certification, raw_url)
    if provider == "coursera":
        valid_coursera_path = re.fullmatch(
            r"/(?:share/[^/]+|account/accomplishments/(?:verify|professional-cert|specialization/certificate)/[^/]+)/?",
            parsed.path,
        )
        if not valid_coursera_path:
            return VerificationResult("rejected", "coursera_url", "Use the certificate's Coursera verification URL, not a course or profile link.")
        return VerificationResult("pending_verification", "coursera_manual", "Coursera provides no public verification API. The official link is tied to Coursera and awaits administrator review.")
    if "credly.com" in parsed.hostname.casefold():
        if not re.fullmatch(r"/badges/[0-9a-fA-F-]+/?", parsed.path):
            return VerificationResult("rejected", "credly_url", "Use the individual Credly badge URL, not a profile or catalogue link.")
        return VerificationResult("pending_verification", "credly_manual", "The official Credly badge link is provider-matched and awaits administrator review.")
    return VerificationResult("pending_verification", "provider_url", "The official provider link was accepted and awaits administrator review.")
