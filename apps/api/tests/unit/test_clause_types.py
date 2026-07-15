"""Unit tests for the priority-weighted clause classifier."""

from leasora_api.services.ingest.clause_types import (
    ClauseType,
    assign_clause_type,
)


def test_rental_term_specific_phrase_wins():
    text = "The monthly rent is $5,000 and rent is due on the first of each month."
    assert assign_clause_type(text) == ClauseType.RENTAL_TERM.value


def test_maintenance_does_not_steal_from_rental_term():
    """Regression: when a clause mentions both maintenance and a specific
    rent phrase, the specific rent phrase must win.

    The highest-weight matching clause type wins, so the specific
    RENTAL_TERM phrase takes precedence over MAINTENANCE when both are present.
    """
    text = (
        "If maintenance of the premises requires the tenant to vacate, "
        "the landlord shall abate the rent due date accordingly."
    )
    assert assign_clause_type(text) == ClauseType.RENTAL_TERM.value


def test_termination_matches_specific_vocabulary():
    text = "Upon breach of any covenant, the landlord may issue a notice to quit."
    assert assign_clause_type(text) == ClauseType.TERMINATION.value


def test_assignment_specific_phrase_beats_generic_assign():
    text = "The tenant shall not assign this lease without the landlord's prior written consent."
    assert assign_clause_type(text) == ClauseType.ASSIGNMENT.value


def test_renewal_specific_phrase_matches():
    text = "This lease shall automatically renew for successive one-year terms unless either party gives notice."
    assert assign_clause_type(text) == ClauseType.RENEWAL.value


def test_liability_matches_specific_vocabulary():
    text = "The tenant shall indemnify the landlord against any liability arising from the tenant's negligence."
    assert assign_clause_type(text) == ClauseType.LIABILITY.value


def test_maintenance_specific_phrase_matches():
    text = "The landlord is responsible for all structural repairs and HVAC maintenance."
    assert assign_clause_type(text) == ClauseType.MAINTENANCE.value


def test_unknown_clause_returns_other():
    text = "This lease supersedes all prior agreements."
    assert assign_clause_type(text) == ClauseType.OTHER.value


def test_assignment_consent_to_assign_phrase_wins_over_generic_assign():
    """Highest-weight phrase: ``consent to assign`` must outrank generic patterns.

    Regression guard for the priority-weighted classifier — clauses that
    mention both the generic ``assign`` word and the high-signal ``consent
    to assign`` phrase MUST classify as ``ASSIGNMENT`` rather than
    something cheaper.
    """
    text = (
        "The Tenant shall not assign this Agreement without the prior written "
        "consent to assign from the Landlord, which consent shall not be "
        "unreasonably withheld."
    )
    assert assign_clause_type(text) == ClauseType.ASSIGNMENT.value


def test_renewal_automatic_renewal_phrase_wins_over_generic_renew():
    """Highest-weight phrase: ``automatic renewal`` must outrank generic patterns.

    A clause that talks about both renewing and the specific ``automatic
    renewal`` phrase MUST classify as ``RENEWAL`` rather than a generic
    fallback that masks the high-signal term.
    """
    text = (
        "Upon expiration of the initial term, this lease shall provide for "
        "automatic renewal for successive one-year terms unless either party "
        "gives written notice of non-renewal at least sixty days prior."
    )
    assert assign_clause_type(text) == ClauseType.RENEWAL.value