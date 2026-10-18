"""Six bundled Indian-context sample documents. Dates are offsets from `today`, so the
Deadlines view always has overdue, within-30-day and later items."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from docmind.models import Document


def _d(today: date, days: int) -> str:
    return (today + timedelta(days=days)).strftime("%d/%m/%Y")


def _long(today: date, days: int) -> str:
    return (today + timedelta(days=days)).strftime("%d %B %Y")


def _texts(today: date) -> dict[str, str]:
    return {
        "Health_Insurance_Policy.txt": f"""\
STAR SHIELD HEALTH INSURANCE - POLICY SCHEDULE

Policy Number: SSH/2025/4471982
Policyholder: Raghav Menon
Insured Members: Raghav Menon (Self), Anjali Menon (Spouse), Kabir Menon (Son)
Insurer: Star Shield General Insurance Co. Ltd.

Policy Period: {_d(today, -340)} to {_d(today, 25)}
Sum Insured: Rs. 10,00,000 (Family Floater)
Annual Premium: ₹24,850 (inclusive of GST)

Renewal: The policy is due for renewal on {_d(today, 25)}. A grace period of 30 days is
allowed for renewal; claims arising during the grace period are not payable.

Waiting Periods: Pre-existing diseases are covered after 36 months of continuous coverage.
Specific illnesses such as cataract and hernia have a waiting period of 24 months.

Room Rent Limit: Up to 1% of the Sum Insured per day (Rs. 10,000 per day).
Co-payment: 10% co-payment applies to all claims for insured members above 60 years.

Cashless claims must be intimated to the TPA at least 48 hours before planned hospitalisation.
""",
        "Car_Insurance_Policy.txt": f"""\
SURAKSHA MOTOR INSURANCE - PRIVATE CAR PACKAGE POLICY

Policy No: SMI-PC-88213457
Insured: Raghav Menon
Vehicle: Hyundai Creta SX, Registration KA-05-MN-4521

Period of Insurance: {_d(today, -320)} to {_d(today, 45)}
Insured Declared Value (IDV): ₹9,40,000
Total Premium Paid: Rs. 18,320
No Claim Bonus: 35%

The policy expires on {_d(today, 45)}. Renew before the expiry date to retain the No Claim Bonus.

Add-ons: Zero Depreciation, Roadside Assistance, Engine Protect.
Compulsory Deductible: Rs. 1,000 per claim.

Accidents must be reported to the insurer within 7 days of the incident.
""",
        "Rental_Agreement.txt": f"""\
RESIDENTIAL RENTAL AGREEMENT

This agreement is made on {_long(today, -200)} between Mr. Suresh Kumar (Landlord) and
Mr. Raghav Menon (Tenant) for the flat at No. 14, 3rd Cross, Indiranagar, Bengaluru 560038.

Term: 11 months, from {_d(today, -200)} to {_d(today, 135)}.
Monthly Rent: ₹32,000, payable on or before the 5th of every month.
Security Deposit: Rs. 1,50,000 (refundable at the end of the tenancy, less any dues).
Maintenance charges of Rs. 2,500 per month are payable by the Tenant.

Notice Period: Either party may terminate this agreement by giving two (2) months' written notice.
Lock-in Period: The first 6 months are a lock-in period.

Rent Increase: Rent shall increase by 5% on renewal of the agreement.
The Tenant shall not sub-let the premises.
""",
        "Broadband_Bill.txt": f"""\
AIRWAVE FIBER - BROADBAND BILL

Account Number: AWF-1029384756
Customer: Raghav Menon
Plan: Fiber Max 300 Mbps (Unlimited)

Bill Date: {_d(today, -20)}
Billing Period: {_d(today, -50)} to {_d(today, -20)}

Plan Charges: Rs. 1,199
GST (18%): Rs. 215.82
Total Amount Due: ₹1,414.82
Payment Due Date: {_d(today, -3)}

A late payment fee of Rs. 100 applies if payment is not received by the due date.
Service may be suspended if dues remain unpaid for 15 days after the due date.
""",
        "Laptop_Warranty.txt": f"""\
WARRANTY CARD - NOVABOOK PRO 14

Product: NovaBook Pro 14 Laptop
Serial Number: NBP14-IN-77310452
Purchased from: Digital Hub Electronics, Bengaluru
Date of Purchase: {_d(today, -350)}
Invoice Amount: ₹84,990

Standard Warranty: 1 year from the date of purchase.
Warranty valid till: {_d(today, 15)}

Extended Warranty: An extended warranty of 2 years can be purchased for Rs. 6,499 before
the standard warranty expires.

The warranty does not cover physical damage, liquid damage or batteries after 6 months.
Service claims require the original invoice and the serial number.
""",
        "Gym_Membership.txt": f"""\
FITZONE GYM - ANNUAL MEMBERSHIP CONTRACT

Member: Raghav Menon
Membership ID: FZ-BLR-20931
Plan: Annual Premium (Gym + Pool)

Start Date: {_d(today, -120)}
End Date: {_d(today, 245)}
Membership Fee: ₹28,000 (paid in full)

Auto-renewal: The membership renews automatically for another year at the then-current fee
unless cancelled in writing at least 30 days before the end date.

Membership Freeze: Members may freeze the membership for up to 30 days per year.
Cancellation: No refund is given for cancellation after the first 14 days.
""",
    }


def build_samples(today: date | None = None) -> list[Document]:
    today = today or date.today()
    docs = []
    for name, text in _texts(today).items():
        raw = text.encode("utf-8")
        docs.append(Document(id=hashlib.sha256(raw).hexdigest()[:12], name=name, source="sample",
                             size_bytes=len(raw), text=text, readable=True))
    return docs


# Suggested questions for the Ask view (the last one is NOT answerable from the samples).
SUGGESTED_QUESTIONS = [
    "When is my health insurance renewal due?",
    "What is the notice period in my rental agreement?",
    "How much is my security deposit?",
    "What is my life insurance policy's death benefit?",
]
