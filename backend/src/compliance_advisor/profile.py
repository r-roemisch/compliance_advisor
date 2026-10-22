"""The Firm Profile: the facts about a Firm that decide which rules apply to it."""

from typing import Literal

from pydantic import BaseModel

FirmType = Literal[
    "significant_bank",  # ECB-supervised (SSM)
    "less_significant_bank",  # BaFin-supervised
    "primary_insurer",
    "reinsurer",
    "insurance_group",
    "payment_institution",
    "e_money_institution",
    "crypto_asset_service_provider",
]
SizeClass = Literal["large", "medium", "small"]
Customers = Literal["retail", "corporate", "both"]
Activity = Literal[
    "life_insurance",
    "health_insurance",
    "non_life_insurance",
    "reinsurance_business",
    "payment_services",
    "cloud_outsourcing",
    "ai_credit_scoring",
    "ai_insurance_pricing",
    "ai_claims_handling",
    "ai_customer_chatbot",
]

BANKS = {"significant_bank", "less_significant_bank"}
INSURERS = {"primary_insurer", "insurance_group", "reinsurer"}
PAYMENT_FIRMS = {"payment_institution", "e_money_institution"}


class FirmProfile(BaseModel, extra="forbid"):
    firm_type: FirmType
    size: SizeClass = "large"
    customers: Customers = "both"
    activities: list[Activity] = []

    def describe(self) -> str:
        activities = ", ".join(self.activities) or "none stated"
        return (
            f"firm type: {self.firm_type}; size: {self.size}; customers: {self.customers}; "
            f"activities: {activities}"
        )


class Preset(BaseModel):
    id: str
    label: dict[str, str]  # {"de": ..., "en": ...}
    profile: FirmProfile


# Presets describe firm types only, never real companies.
PRESETS = [
    Preset(
        id="insurance-group-large",
        label={"de": "Versicherungsgruppe, groß", "en": "Insurance group, large"},
        profile=FirmProfile(
            firm_type="insurance_group",
            size="large",
            customers="both",
            activities=[
                "life_insurance",
                "health_insurance",
                "non_life_insurance",
                "cloud_outsourcing",
                "ai_insurance_pricing",
                "ai_claims_handling",
                "ai_customer_chatbot",
            ],
        ),
    ),
    Preset(
        id="reinsurer-large",
        label={"de": "Rückversicherer, groß", "en": "Reinsurer, large"},
        profile=FirmProfile(
            firm_type="reinsurer",
            size="large",
            customers="corporate",
            activities=["reinsurance_business", "cloud_outsourcing", "ai_claims_handling"],
        ),
    ),
    Preset(
        id="life-insurer-medium",
        label={"de": "Lebensversicherer, mittelgroß", "en": "Life insurer, medium-sized"},
        profile=FirmProfile(
            firm_type="primary_insurer",
            size="medium",
            customers="retail",
            activities=["life_insurance", "cloud_outsourcing", "ai_insurance_pricing"],
        ),
    ),
    Preset(
        id="significant-bank",
        label={
            "de": "Bedeutendes Institut (EZB-Aufsicht)",
            "en": "Significant bank (ECB-supervised)",
        },
        profile=FirmProfile(
            firm_type="significant_bank",
            size="large",
            customers="both",
            activities=["payment_services", "cloud_outsourcing", "ai_credit_scoring"],
        ),
    ),
    Preset(
        id="less-significant-bank",
        label={
            "de": "Weniger bedeutendes Institut (BaFin-Aufsicht)",
            "en": "Less significant bank (BaFin-supervised)",
        },
        profile=FirmProfile(
            firm_type="less_significant_bank",
            size="medium",
            customers="retail",
            activities=["payment_services", "cloud_outsourcing"],
        ),
    ),
    Preset(
        id="payment-institution-small",
        label={"de": "Zahlungsinstitut, klein", "en": "Payment institution, small"},
        profile=FirmProfile(
            firm_type="payment_institution",
            size="small",
            customers="retail",
            activities=["payment_services", "cloud_outsourcing", "ai_customer_chatbot"],
        ),
    ),
]
