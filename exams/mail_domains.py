"""Does an email domain accept mail at all? Catches typos (gmial.com) before an invitation is queued.

Only the domain can be checked this way: a missing mailbox at a real domain is reported later by
a bounce (see bounces.py). DNS trouble never blocks an invitation: the answer is then "unknown".
"""

import logging

import dns.exception
import dns.resolver
from django.conf import settings

logger = logging.getLogger("exams.outbox")
DNS_TIMEOUT_SECONDS = 3.0


def _has_address(resolver, domain: str) -> bool:
    """RFC 5321 implicit MX: without MX records, mail goes to the domain's A/AAAA address."""
    for record_type in ("A", "AAAA"):
        try:
            resolver.resolve(domain, record_type)
            return True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            continue
    return False


def domain_accepts_mail(email: str) -> bool | None:
    """True or False when DNS answers clearly; None when it could not be determined."""
    domain = email.rsplit("@", 1)[-1].strip().rstrip(".")
    resolver = dns.resolver.Resolver()
    resolver.lifetime = DNS_TIMEOUT_SECONDS
    try:
        answer = resolver.resolve(domain, "MX")
        # RFC 7505 "null MX" (a single "." exchange) declares that the domain receives no mail.
        return any(record.exchange.to_text() != "." for record in answer)
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        try:
            return _has_address(resolver, domain)
        except dns.exception.DNSException:
            return None
    except dns.exception.DNSException as error:
        logger.warning("mail domain check inconclusive (%s)", type(error).__name__)
        return None


def undeliverable(email: str) -> bool:
    """Refuse only a clear "no". Skipped when emails are not really sent (console mode)."""
    return settings.EMAIL_ENABLED and domain_accepts_mail(email) is False
