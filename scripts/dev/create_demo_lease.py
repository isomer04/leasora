"""
Generate demo_lease.pdf — a realistic 4-page California residential lease
that exercises every clause type in config.CLAUSE_TYPES so the Leasora
pipeline can be fully tested end-to-end.

Run:  python create_demo_lease.py
Output: demo_lease.pdf
"""

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT = "demo_lease.pdf"
W, H = letter

# Styles

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "Title",
    parent=styles["Heading1"],
    fontSize=16,
    leading=20,
    alignment=TA_CENTER,
    spaceAfter=4,
)
subtitle_style = ParagraphStyle(
    "Subtitle",
    parent=styles["Normal"],
    fontSize=10,
    leading=13,
    alignment=TA_CENTER,
    spaceAfter=2,
)
section_style = ParagraphStyle(
    "Section",
    parent=styles["Heading2"],
    fontSize=11,
    leading=14,
    spaceBefore=10,
    spaceAfter=4,
    textColor=colors.HexColor("#1a1a1a"),
)
body_style = ParagraphStyle(
    "Body",
    parent=styles["Normal"],
    fontSize=9.5,
    leading=14,
    alignment=TA_JUSTIFY,
    spaceAfter=6,
)
bold_body = ParagraphStyle(
    "BoldBody",
    parent=body_style,
    fontName="Helvetica-Bold",
)
small_style = ParagraphStyle(
    "Small",
    parent=styles["Normal"],
    fontSize=8,
    leading=11,
    alignment=TA_CENTER,
    textColor=colors.HexColor("#555555"),
)

# Helper

def S(n=6):
    return Spacer(1, n)


def HR():
    return HRFlowable(
        width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=4
    )


def sec(num, title):
    return Paragraph(f"{num}. {title.upper()}", section_style)


def body(text):
    return Paragraph(text, body_style)


def bold(text):
    return Paragraph(text, bold_body)


# Document

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=letter,
    leftMargin=1 * inch,
    rightMargin=1 * inch,
    topMargin=0.85 * inch,
    bottomMargin=0.85 * inch,
)

story = []

# PAGE 1 — Cover & Parties / Rent / Security Deposit / Lease Term

story += [
    Paragraph("RESIDENTIAL LEASE AGREEMENT", title_style),
    Paragraph(
        "State of California — Governed by California Civil Code §§ 1940–1954.06",
        subtitle_style,
    ),
    Paragraph(
        "THIS DOCUMENT IS FOR TESTING PURPOSES — LEASORA DEMO FILE", subtitle_style
    ),
    S(4),
    HR(),
    S(6),
]

# Parties table
party_data = [
    [bold("LANDLORD"), bold("TENANT")],
    [
        body(
            "Margaret L. Holloway\n123 Sunset Blvd, Suite 4\nLos Angeles, CA 90028\nPhone: (213) 555-0192\nEmail: mholloway@example.com"
        ),
        body(
            "Daniel A. Reyes\n(Current address) 88 Oak Street, Apt 2B\nPasadena, CA 91103\nPhone: (626) 555-0477\nEmail: dan.reyes@example.com"
        ),
    ],
]
party_table = Table(party_data, colWidths=[3.0 * inch, 3.0 * inch])
party_table.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]
    )
)
story += [party_table, S(10)]

# Premises summary table
info_data = [
    ["Rental Property:", "4401 Willow Creek Drive, Apt 7C, Los Angeles, CA 90027"],
    ["Lease Start Date:", "August 1, 2025"],
    ["Lease End Date:", "July 31, 2026  (12-month term)"],
    ["Monthly Rent:", "$2,850.00"],
    ["Security Deposit:", "$5,700.00  (equal to two months' rent)"],
    ["Rent Due Date:", "1st of each month"],
    ["Grace Period:", "5 calendar days"],
]
info_table = Table(info_data, colWidths=[1.8 * inch, 4.2 * inch])
info_table.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f7f7f7")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("LEADING", (0, 0), (-1, -1), 14),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]
    )
)
story += [info_table, S(12)]

# Section 1 — Lease Term & Renewal
story += [
    sec("1", "Lease Term & Renewal"),
    body(
        "1.1  This Agreement commences on <b>August 1, 2025</b> and expires on "
        '<b>July 31, 2026</b> (the "Lease Term"). Tenant shall vacate the '
        "premises no later than 11:59 PM on the expiration date unless a written "
        "renewal is executed by both parties."
    ),
    body(
        "1.2  <b>Month-to-Month Conversion.</b> If Tenant remains in possession "
        "after the expiration date without a signed renewal, the tenancy shall "
        "automatically convert to a month-to-month tenancy at the same rent, "
        "subject to California Civil Code § 1946. Either party may terminate the "
        "month-to-month tenancy with <b>30 days' written notice</b>."
    ),
    body(
        "1.3  <b>Renewal Option.</b> Tenant may request a 12-month renewal by "
        "providing written notice no later than <b>60 days before lease expiration</b>. "
        "Landlord shall respond within 14 days. Renewal rent shall not exceed the "
        "prior monthly rent plus 5% or CPI, whichever is lower, per California "
        "AB 1482 (Tenant Protection Act of 2019)."
    ),
    S(4),
]

# Section 2 — Rent & Late Fees
story += [
    sec("2", "Rent & Late Fees"),
    body(
        "2.1  Tenant agrees to pay <b>$2,850.00 per month</b> as base rent, due "
        "on the <b>1st day of each calendar month</b>, payable by check, ACH "
        "transfer, or Landlord's approved online portal (Venmo and cash are not "
        "accepted). Rent is considered received on the date it clears Landlord's "
        "account."
    ),
    body(
        "2.2  <b>Late Fee.</b> If rent is not received by the <b>6th of the month</b> "
        "(after a 5-day grace period), a late fee of <b>$75.00</b> per day shall "
        "accrue until the balance is paid in full. <b>⚠ RED FLAG NOTE:</b> A "
        "per-day late fee is above California norms; standard practice is a "
        "one-time fee of 5–6% of monthly rent (~$142–$171 one-time). Tenants "
        "should negotiate this clause before signing."
    ),
    body(
        "2.3  <b>Returned Check Fee.</b> A fee of $35.00 shall be charged for "
        "any check returned for insufficient funds. After two returned checks, "
        "Landlord may require all future payments by cashier's check or money order."
    ),
    body(
        "2.4  <b>Rent Increases.</b> During the Lease Term, rent shall not "
        "increase. Subsequent increases shall comply with California AB 1482, "
        "capped at 5% + local CPI (max 10%) per 12-month period."
    ),
    PageBreak(),
]

# PAGE 2 — Security Deposit / Early Termination / Subletting / Pets

story += [
    Paragraph("RESIDENTIAL LEASE AGREEMENT  —  PAGE 2", subtitle_style),
    HR(),
    S(8),
]

# Section 3 — Security Deposit
story += [
    sec("3", "Security Deposit"),
    body(
        "3.1  Tenant shall pay a security deposit of <b>$5,700.00</b> (equal to "
        "two months' rent) prior to or upon move-in. The deposit is held by "
        "Landlord in a <b>non-interest-bearing account</b> at Wells Fargo Bank, "
        "Los Angeles branch. Landlord is not required to pay Tenant interest on "
        "the deposit."
    ),
    body(
        "3.2  <b>Allowable Deductions.</b> Landlord may deduct from the security "
        "deposit: (a) unpaid rent; (b) costs to repair damages beyond normal wear "
        "and tear; (c) cleaning fees if the unit is not returned in the same "
        "condition as at move-in (reasonable wear and tear excepted); (d) costs "
        "for replacing Landlord's personal property taken by Tenant."
    ),
    body(
        "3.3  <b>Return Deadline.</b> Landlord shall return the deposit (or a "
        "written itemized statement of deductions with remaining balance) within "
        "<b>21 calendar days</b> after Tenant vacates, per California Civil Code "
        "§ 1950.5. Failure to meet this deadline forfeits Landlord's right to "
        "make any deductions."
    ),
    body(
        "3.4  <b>Move-In / Move-Out Inspection.</b> Landlord shall provide Tenant "
        "with a written move-in checklist within 3 days of occupancy. Tenant "
        "has the right to request a pre-move-out inspection no earlier than "
        "14 days before the termination date (CA Civil Code § 1950.5(f))."
    ),
    S(4),
]

# Section 4 — Early Termination
story += [
    sec("4", "Early Termination"),
    body(
        "4.1  <b>Tenant Early Termination Fee.</b> If Tenant terminates this "
        "Agreement before July 31, 2026, Tenant shall pay an early termination "
        "fee equal to <b>two months' rent ($5,700.00)</b>, plus forfeit the "
        "security deposit, plus reimburse Landlord for any unpaid rent through "
        "the earlier of: (i) the date a replacement tenant begins paying rent, "
        "or (ii) the original lease end date. <b>⚠ RED FLAG:</b> Stacking an "
        "early-termination fee on top of deposit forfeiture and continued rent "
        "liability is unusually punitive; California law does not require "
        "Tenants to pay more than actual damages."
    ),
    body(
        "4.2  <b>Military Clause.</b> Notwithstanding Section 4.1, a Tenant "
        "who receives qualifying military orders for permanent change of station "
        "or deployment of more than 90 days may terminate with 30 days' written "
        "notice and proof of orders, per the Servicemembers Civil Relief Act "
        "(50 U.S.C. § 3955). No early termination fee shall apply."
    ),
    body(
        "4.3  <b>Landlord Termination for Cause.</b> Landlord may terminate "
        "with 3 days' notice for non-payment of rent, material lease violations, "
        "or illegal use of the premises, per California Code of Civil Procedure "
        "§ 1161."
    ),
    S(4),
]

# Section 5 — Subletting & Assignment
story += [
    sec("5", "Subletting & Assignment"),
    body(
        "5.1  Tenant shall <b>not sublet</b> the premises or any portion thereof, "
        "nor assign this Agreement or any interest herein, without the prior "
        "written consent of Landlord, which shall not be unreasonably withheld "
        "(California Civil Code § 1995.010 et seq.)."
    ),
    body(
        "5.2  Any request to sublet or assign must be submitted in writing at "
        "least <b>30 days in advance</b> and include: (a) the proposed subtenant's "
        "full name; (b) current address; (c) employment verification; (d) credit "
        "report. Landlord shall respond within 14 days of receiving a complete "
        "request. Silence beyond 14 days shall not constitute consent."
    ),
    body(
        "5.3  Short-term rental platforms (e.g., Airbnb, VRBO) are expressly "
        "<b>prohibited</b> under this Agreement. Any unauthorized short-term "
        "rental is grounds for lease termination under Section 4.3."
    ),
    S(4),
]

# Section 6 — Pets
story += [
    sec("6", "Pets"),
    body(
        "6.1  <b>No pets</b> of any kind are permitted in or about the premises "
        "without prior written consent of Landlord. This includes dogs, cats, "
        "birds, reptiles, rodents, and fish tanks over 10 gallons."
    ),
    body(
        "6.2  <b>Pet Deposit (if approved).</b> Upon written approval, Tenant "
        "shall pay an additional refundable pet deposit of <b>$500.00 per pet</b> "
        "(max two pets). This deposit is subject to the same deduction rules as "
        "Section 3.2. Note: California law does not cap pet deposits separately; "
        "however, total deposits (including pet) cannot exceed three months' rent "
        "for unfurnished units."
    ),
    body(
        "6.3  <b>Service Animals & ESAs.</b> Landlord shall make reasonable "
        "accommodations for verified service animals and emotional support "
        "animals as required by the Fair Housing Act and California FEHA. "
        "A pet deposit may not be charged for a verified service animal."
    ),
    PageBreak(),
]

# PAGE 3 — Maintenance / Utilities / Entry & Privacy / Alterations / Use

story += [
    Paragraph("RESIDENTIAL LEASE AGREEMENT  —  PAGE 3", subtitle_style),
    HR(),
    S(8),
]

# Section 7 — Maintenance & Repairs
story += [
    sec("7", "Maintenance & Repairs"),
    body(
        "7.1  <b>Landlord Obligations.</b> Landlord shall maintain the premises "
        "in a habitable condition per California Civil Code § 1941, including: "
        "functioning heating, plumbing, electrical systems; weatherproofing; "
        "pest control for infestations not caused by Tenant; and structural "
        "safety of floors, walls, and roof."
    ),
    body(
        "7.2  <b>Tenant Obligations.</b> Tenant shall: (a) keep the unit clean "
        "and sanitary; (b) properly dispose of garbage; (c) not intentionally "
        "damage fixtures; (d) promptly report any needed repairs to Landlord "
        "in writing."
    ),
    body(
        "7.3  <b>Repair Request Response Time.</b> Landlord shall begin repairs "
        "within <b>30 days</b> of written notice for non-emergency issues, and "
        "within <b>24 hours</b> for emergencies (loss of heat, water, electrical "
        "failure, gas leak). If Landlord fails to repair within the statutory "
        "period, Tenant may exercise rights under California Civil Code § 1942 "
        "(repair-and-deduct, up to one month's rent per repair event)."
    ),
    body(
        "7.4  <b>Appliances.</b> The following appliances are provided by "
        "Landlord in working order: refrigerator, dishwasher, oven/range, "
        "microwave, washer/dryer (in-unit). Landlord shall repair or replace "
        "within 14 days of notification of malfunction."
    ),
    S(4),
]

# Section 8 — Utilities
story += [
    sec("8", "Utilities"),
    body(
        "8.1  <b>Landlord-Paid Utilities:</b> Water, sewer, and trash removal "
        "are included in the monthly rent. Landlord shall maintain these services "
        "without interruption except for scheduled maintenance with 48 hours' notice."
    ),
    body(
        "8.2  <b>Tenant-Paid Utilities:</b> Tenant is solely responsible for "
        "establishing and paying accounts for electricity, gas (SoCalGas), "
        "internet, and cable. Tenant shall open utility accounts in their own "
        "name no later than the lease start date."
    ),
    body(
        "8.3  <b>RUBS (Ratio Utility Billing System).</b> Landlord reserves the "
        "right to implement a RUBS program for water and trash with 30 days' "
        "written notice, not to exceed $60/month combined. <b>UNUSUAL:</b> "
        "Shifting currently-included utilities to Tenant mid-tenancy via RUBS "
        "is contested under California law (AB 2379 pending); Tenant may wish "
        "to request removal of this clause."
    ),
    S(4),
]

# Section 9 — Entry & Privacy
story += [
    sec("9", "Entry & Privacy"),
    body(
        "9.1  <b>Notice Requirement.</b> Landlord shall provide Tenant with "
        "<b>24 hours' written notice</b> before entering the premises for "
        "non-emergency purposes (inspections, repairs, showings), per California "
        "Civil Code § 1954. Entry shall occur only between 8:00 AM and 6:00 PM "
        "on weekdays unless Tenant consents in writing to a different time."
    ),
    body(
        "9.2  <b>Emergency Entry.</b> Landlord may enter without notice in the "
        "event of a genuine emergency (fire, flood, gas leak, imminent danger "
        "to property or persons)."
    ),
    body(
        "9.3  <b>Frequency of Inspections.</b> Routine inspections are limited "
        "to <b>once per calendar quarter</b>. Landlord may not conduct inspections "
        "more frequently except when work orders are active or at Tenant request."
    ),
    body(
        "9.4  <b>Smart Home Devices.</b> Landlord may install and maintain a "
        "smart doorbell camera at the front door only. No recording devices "
        "shall be installed inside the unit. Tenant may install their own "
        "security devices with Landlord's written approval."
    ),
    S(4),
]

# Section 10 — Alterations
story += [
    sec("10", "Alterations"),
    body(
        "10.1  Tenant shall not make any structural alterations, additions, or "
        "improvements to the premises without prior written consent of Landlord. "
        "This includes but is not limited to: painting walls (colors other than "
        "original), installing shelving that requires studs, removing or adding "
        "doors, or modifying electrical or plumbing systems."
    ),
    body(
        "10.2  <b>Permitted Minor Alterations.</b> Tenant may: (a) hang pictures "
        'and shelves using standard fasteners up to 1/4" diameter; (b) install '
        "removable window treatments; (c) add door locks with Landlord's written "
        "approval (duplicate keys to be provided to Landlord)."
    ),
    body(
        "10.3  <b>Restoration.</b> Upon vacating, Tenant shall restore the "
        "premises to its original condition, including patching and painting "
        "any wall holes. Costs not restored shall be deducted from the security "
        "deposit per Section 3.2."
    ),
    S(4),
]

# Section 11 — Use & Occupancy
story += [
    sec("11", "Use & Occupancy"),
    body(
        "11.1  The premises shall be used solely as a private residential "
        "dwelling for Tenant and the following approved occupants: "
        "<b>Daniel A. Reyes</b> (Tenant), plus one additional adult occupant "
        "pending Landlord approval. No additional permanent occupants may reside "
        "in the unit without prior written consent."
    ),
    body(
        "11.2  <b>Prohibited Uses.</b> Tenant shall not: (a) operate any "
        "commercial business from the premises; (b) use the unit for any "
        "illegal purpose; (c) store hazardous materials; (d) conduct activities "
        "that disturb neighbors between 10:00 PM and 8:00 AM."
    ),
    body(
        "11.3  <b>Parking.</b> One (1) assigned parking space (#7C) is included. "
        "Tenant may not sublet or share the parking space. Guest parking is "
        "limited to 48 consecutive hours."
    ),
    PageBreak(),
]

# PAGE 4 — Insurance / Wear & Tear / Dispute Resolution / Signatures

story += [
    Paragraph("RESIDENTIAL LEASE AGREEMENT  —  PAGE 4", subtitle_style),
    HR(),
    S(8),
]

# Section 12 — Insurance & Liability
story += [
    sec("12", "Insurance & Liability"),
    body(
        "12.1  <b>Renter's Insurance Required.</b> Tenant shall obtain and "
        "maintain a renter's insurance policy throughout the Lease Term with "
        "minimum coverage of <b>$100,000 personal liability</b> and <b>$20,000 "
        "personal property</b>. Proof of insurance must be provided to Landlord "
        "within 14 days of lease commencement and upon each renewal. "
        "<b>UNUSUAL:</b> Mandatory renter's insurance is becoming more common "
        "but is not required by California law; failure to comply is typically "
        "a lease violation but not automatic grounds for eviction."
    ),
    body(
        "12.2  <b>Landlord's Insurance.</b> Landlord maintains a property "
        "insurance policy covering the building structure. Landlord's insurance "
        "does not cover Tenant's personal property or Tenant's liability."
    ),
    body(
        "12.3  <b>Indemnification.</b> Tenant shall indemnify and hold harmless "
        "Landlord from claims, losses, or damages arising from Tenant's negligent "
        "or intentional acts within the premises. Landlord shall indemnify "
        "Tenant from claims arising from Landlord's negligence or failure to "
        "maintain the premises."
    ),
    S(4),
]

# Section 13 — Wear and Tear
story += [
    sec("13", "Wear and Tear"),
    body(
        '13.1  <b>Normal Wear and Tear Defined.</b> "Normal wear and tear" means '
        "deterioration that occurs through reasonable use of the premises, "
        "including: minor scuffs on walls from furniture, carpet wear from "
        "normal foot traffic, small nail holes from hanging pictures, and faded "
        "paint due to sunlight exposure. These shall not be charged to Tenant."
    ),
    body(
        "13.2  <b>Damage Beyond Normal Wear.</b> The following shall be "
        "considered damage beyond normal wear and deducted from the security "
        "deposit: large holes in walls, burns on carpet or countertops, stains "
        "that cannot be removed by professional cleaning, broken fixtures, "
        "missing or damaged blinds, and unauthorized paint colors."
    ),
    body(
        "13.3  <b>Carpet & Paint Lifespan.</b> Carpet shall be deemed at end "
        "of useful life after <b>7 years</b> (consistent with CA guidelines); "
        "paint after <b>2 years</b>. If either has surpassed useful life at "
        "move-out, Tenant shall not be charged for full replacement — only "
        "prorated costs for damage in excess of normal wear, if any."
    ),
    S(4),
]

# Section 14 — Dispute Resolution
story += [
    sec("14", "Dispute Resolution"),
    body(
        "14.1  <b>Good-Faith Negotiation.</b> The parties agree to attempt "
        "resolution of any dispute through direct good-faith negotiation for "
        "no less than 14 calendar days before pursuing other remedies."
    ),
    body(
        "14.2  <b>Mediation.</b> If negotiation fails, the parties agree to "
        "participate in non-binding mediation through the Los Angeles County "
        "Department of Consumer and Business Affairs (DCBA) Rent Stabilization "
        "program or a mutually agreed mediator, at shared cost."
    ),
    body(
        "14.3  <b>Arbitration Waiver.</b> Notwithstanding the foregoing, "
        "<b>neither party waives the right to bring an action in small claims "
        "court</b> (for claims within CA Small Claims limits) or to seek "
        "emergency injunctive relief in a court of competent jurisdiction. "
        "This Agreement does not contain a binding arbitration clause."
    ),
    body(
        "14.4  <b>Attorney's Fees.</b> In any legal action arising from this "
        "Agreement, the prevailing party shall be entitled to recover reasonable "
        "attorney's fees and court costs, per California Civil Code § 1717."
    ),
    body(
        "14.5  <b>Governing Law & Venue.</b> This Agreement is governed by the "
        "laws of the State of California. Any action shall be brought in Los "
        "Angeles County Superior Court."
    ),
    S(8),
]

# Section 15 — General Provisions
story += [
    sec("15", "General Provisions"),
    body(
        "15.1  <b>Entire Agreement.</b> This Agreement, together with any "
        "attached addenda, constitutes the entire agreement between the parties "
        "and supersedes all prior oral or written negotiations."
    ),
    body(
        "15.2  <b>Severability.</b> If any provision is found invalid or "
        "unenforceable, the remainder of the Agreement shall continue in full "
        "force and effect."
    ),
    body(
        "15.3  <b>Notices.</b> All notices must be in writing and delivered by: "
        "(a) personal delivery; (b) first-class mail; or (c) email with read "
        "receipt to the addresses in this Agreement. Notice by email is effective "
        "upon confirmed delivery."
    ),
    S(12),
    HR(),
]

# Signature block
sig_data = [
    [bold("LANDLORD SIGNATURE"), bold("TENANT SIGNATURE")],
    [
        body(
            "Signature: _____________________________\n\n"
            "Name: Margaret L. Holloway\n\n"
            "Date: _____________"
        ),
        body(
            "Signature: _____________________________\n\n"
            "Name: Daniel A. Reyes\n\n"
            "Date: _____________"
        ),
    ],
]
sig_table = Table(sig_data, colWidths=[3.0 * inch, 3.0 * inch])
sig_table.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]
    )
)
story += [sig_table, S(10)]

story += [
    Paragraph(
        "⚠ THIS IS A DEMO DOCUMENT FOR LEASORA TESTING PURPOSES ONLY. "
        "NOT A LEGALLY BINDING AGREEMENT. NOT LEGAL ADVICE.",
        small_style,
    )
]

# Build

if __name__ == "__main__":
    doc.build(story)
    print(f"✅  Created {OUTPUT}  —  4 pages, 15 sections, all clause types covered.")