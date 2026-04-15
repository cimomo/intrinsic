"""
Damodaran's industry betas for bottom-up beta computation.

Source: https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls
Last updated: 2026-01-05
Industries: 94

Each entry includes:
- n_firms: number of firms in the industry sample
- de_ratio: average market debt-to-equity for the industry
- unlevered_beta: industry-average unlevered beta (uncorrected for cash)
- cash_firm_value: industry-average cash / firm value
- unlevered_beta_corrected: cash-corrected unlevered beta (Damodaran's
  recommended pure-play beta -- see his FAQ on the betas dataset page)

The cash-corrected column is computed as: unlevered_beta / (1 - cash_firm_value).
This module uses unlevered_beta_corrected as the input to compute_bottom_up_beta.

Update annually when Damodaran refreshes betas.xls (typically January).
To regenerate: re-run the data extraction described in
docs/superpowers/plans/2026-04-14-bottom-up-beta.md, Task 1.
"""

from typing import Dict, Optional

DAMODARAN_BETAS_DATE = "2026-01-05"

DAMODARAN_BETAS: Dict[str, Dict] = {
    "Advertising": {"n_firms": 52, "de_ratio": 0.4020, "unlevered_beta": 0.9301, "cash_firm_value": 0.0773, "unlevered_beta_corrected": 1.0080},
    "Aerospace/Defense": {"n_firms": 79, "de_ratio": 0.1556, "unlevered_beta": 0.8467, "cash_firm_value": 0.0261, "unlevered_beta_corrected": 0.8694},
    "Air Transport": {"n_firms": 23, "de_ratio": 0.9117, "unlevered_beta": 0.7041, "cash_firm_value": 0.0711, "unlevered_beta_corrected": 0.7579},
    "Apparel": {"n_firms": 35, "de_ratio": 0.3129, "unlevered_beta": 0.7580, "cash_firm_value": 0.0460, "unlevered_beta_corrected": 0.7946},
    "Auto & Truck": {"n_firms": 33, "de_ratio": 0.1970, "unlevered_beta": 1.2690, "cash_firm_value": 0.0299, "unlevered_beta_corrected": 1.3082},
    "Auto Parts": {"n_firms": 35, "de_ratio": 0.4146, "unlevered_beta": 1.0217, "cash_firm_value": 0.0945, "unlevered_beta_corrected": 1.1283},
    "Bank (Money Center)": {"n_firms": 15, "de_ratio": 1.6419, "unlevered_beta": 0.3411, "cash_firm_value": 0.2317, "unlevered_beta_corrected": 0.4439},
    "Banks (Regional)": {"n_firms": 568, "de_ratio": 0.5210, "unlevered_beta": 0.2865, "cash_firm_value": 0.2348, "unlevered_beta_corrected": 0.3744},
    "Beverage (Alcoholic)": {"n_firms": 14, "de_ratio": 0.4334, "unlevered_beta": 0.6132, "cash_firm_value": 0.0237, "unlevered_beta_corrected": 0.6280},
    "Beverage (Soft)": {"n_firms": 27, "de_ratio": 0.2059, "unlevered_beta": 0.5557, "cash_firm_value": 0.0344, "unlevered_beta_corrected": 0.5755},
    "Broadcasting": {"n_firms": 24, "de_ratio": 0.8585, "unlevered_beta": 0.2864, "cash_firm_value": 0.0918, "unlevered_beta_corrected": 0.3153},
    "Brokerage & Investment Banking": {"n_firms": 32, "de_ratio": 1.3557, "unlevered_beta": 0.5808, "cash_firm_value": 0.1451, "unlevered_beta_corrected": 0.6794},
    "Building Materials": {"n_firms": 41, "de_ratio": 0.2600, "unlevered_beta": 0.9302, "cash_firm_value": 0.0316, "unlevered_beta_corrected": 0.9605},
    "Business & Consumer Services": {"n_firms": 155, "de_ratio": 0.1972, "unlevered_beta": 0.7736, "cash_firm_value": 0.0402, "unlevered_beta_corrected": 0.8060},
    "Cable TV": {"n_firms": 9, "de_ratio": 1.4694, "unlevered_beta": 0.3524, "cash_firm_value": 0.0289, "unlevered_beta_corrected": 0.3629},
    "Chemical (Basic)": {"n_firms": 29, "de_ratio": 0.9935, "unlevered_beta": 0.5800, "cash_firm_value": 0.0891, "unlevered_beta_corrected": 0.6368},
    "Chemical (Diversified)": {"n_firms": 4, "de_ratio": 1.7611, "unlevered_beta": 0.3666, "cash_firm_value": 0.0975, "unlevered_beta_corrected": 0.4061},
    "Chemical (Specialty)": {"n_firms": 59, "de_ratio": 0.2988, "unlevered_beta": 0.7922, "cash_firm_value": 0.0391, "unlevered_beta_corrected": 0.8245},
    "Coal & Related Energy": {"n_firms": 16, "de_ratio": 0.0714, "unlevered_beta": 1.0165, "cash_firm_value": 0.1403, "unlevered_beta_corrected": 1.1824},
    "Computer Services": {"n_firms": 64, "de_ratio": 0.2510, "unlevered_beta": 0.9155, "cash_firm_value": 0.0480, "unlevered_beta_corrected": 0.9617},
    "Computers/Peripherals": {"n_firms": 36, "de_ratio": 0.0462, "unlevered_beta": 1.3051, "cash_firm_value": 0.0147, "unlevered_beta_corrected": 1.3246},
    "Construction Supplies": {"n_firms": 40, "de_ratio": 0.1762, "unlevered_beta": 1.0161, "cash_firm_value": 0.0294, "unlevered_beta_corrected": 1.0468},
    "Diversified": {"n_firms": 20, "de_ratio": 0.1555, "unlevered_beta": 0.7889, "cash_firm_value": 0.0642, "unlevered_beta_corrected": 0.8431},
    "Drugs (Biotechnology)": {"n_firms": 496, "de_ratio": 0.1304, "unlevered_beta": 1.0341, "cash_firm_value": 0.0420, "unlevered_beta_corrected": 1.0795},
    "Drugs (Pharmaceutical)": {"n_firms": 228, "de_ratio": 0.1454, "unlevered_beta": 0.8862, "cash_firm_value": 0.0316, "unlevered_beta_corrected": 0.9151},
    "Education": {"n_firms": 32, "de_ratio": 0.2438, "unlevered_beta": 0.6602, "cash_firm_value": 0.0826, "unlevered_beta_corrected": 0.7196},
    "Electrical Equipment": {"n_firms": 112, "de_ratio": 0.1200, "unlevered_beta": 1.1478, "cash_firm_value": 0.0353, "unlevered_beta_corrected": 1.1898},
    "Electronics (Consumer & Office)": {"n_firms": 8, "de_ratio": 0.0580, "unlevered_beta": 0.8299, "cash_firm_value": 0.1052, "unlevered_beta_corrected": 0.9274},
    "Electronics (General)": {"n_firms": 114, "de_ratio": 0.1101, "unlevered_beta": 0.8974, "cash_firm_value": 0.0428, "unlevered_beta_corrected": 0.9375},
    "Engineering/Construction": {"n_firms": 48, "de_ratio": 0.1401, "unlevered_beta": 1.0949, "cash_firm_value": 0.0374, "unlevered_beta_corrected": 1.1374},
    "Entertainment": {"n_firms": 92, "de_ratio": 0.1591, "unlevered_beta": 0.7372, "cash_firm_value": 0.0336, "unlevered_beta_corrected": 0.7628},
    "Environmental & Waste Services": {"n_firms": 53, "de_ratio": 0.2145, "unlevered_beta": 0.8145, "cash_firm_value": 0.0125, "unlevered_beta_corrected": 0.8248},
    "Farming/Agriculture": {"n_firms": 35, "de_ratio": 0.5185, "unlevered_beta": 0.8130, "cash_firm_value": 0.0387, "unlevered_beta_corrected": 0.8458},
    "Financial Svcs. (Non-bank & Insurance)": {"n_firms": 176, "de_ratio": 2.7213, "unlevered_beta": 0.3189, "cash_firm_value": 0.0269, "unlevered_beta_corrected": 0.3277},
    "Food Processing": {"n_firms": 78, "de_ratio": 0.4373, "unlevered_beta": 0.4574, "cash_firm_value": 0.0256, "unlevered_beta_corrected": 0.4694},
    "Food Wholesalers": {"n_firms": 13, "de_ratio": 0.4697, "unlevered_beta": 0.6409, "cash_firm_value": 0.0106, "unlevered_beta_corrected": 0.6478},
    "Furn/Home Furnishings": {"n_firms": 27, "de_ratio": 0.4233, "unlevered_beta": 0.6248, "cash_firm_value": 0.0419, "unlevered_beta_corrected": 0.6521},
    "Green & Renewable Energy": {"n_firms": 15, "de_ratio": 1.1311, "unlevered_beta": 0.4633, "cash_firm_value": 0.0190, "unlevered_beta_corrected": 0.4723},
    "Healthcare Products": {"n_firms": 204, "de_ratio": 0.1279, "unlevered_beta": 0.8291, "cash_firm_value": 0.0325, "unlevered_beta_corrected": 0.8569},
    "Healthcare Support Services": {"n_firms": 104, "de_ratio": 0.3543, "unlevered_beta": 0.6889, "cash_firm_value": 0.0751, "unlevered_beta_corrected": 0.7449},
    "Heathcare Information and Technology": {"n_firms": 115, "de_ratio": 0.1574, "unlevered_beta": 0.9913, "cash_firm_value": 0.0246, "unlevered_beta_corrected": 1.0163},
    "Homebuilding": {"n_firms": 30, "de_ratio": 0.2134, "unlevered_beta": 0.7850, "cash_firm_value": 0.0800, "unlevered_beta_corrected": 0.8532},
    "Hospitals/Healthcare Facilities": {"n_firms": 31, "de_ratio": 0.5992, "unlevered_beta": 0.5517, "cash_firm_value": 0.0232, "unlevered_beta_corrected": 0.5649},
    "Hotel/Gaming": {"n_firms": 63, "de_ratio": 0.3975, "unlevered_beta": 0.8323, "cash_firm_value": 0.0496, "unlevered_beta_corrected": 0.8757},
    "Household Products": {"n_firms": 110, "de_ratio": 0.1815, "unlevered_beta": 0.7178, "cash_firm_value": 0.0314, "unlevered_beta_corrected": 0.7411},
    "Information Services": {"n_firms": 15, "de_ratio": 0.3317, "unlevered_beta": 0.7372, "cash_firm_value": 0.0254, "unlevered_beta_corrected": 0.7564},
    "Insurance (General)": {"n_firms": 21, "de_ratio": 0.2563, "unlevered_beta": 0.5636, "cash_firm_value": 0.0250, "unlevered_beta_corrected": 0.5781},
    "Insurance (Life)": {"n_firms": 20, "de_ratio": 0.6784, "unlevered_beta": 0.4272, "cash_firm_value": 0.1967, "unlevered_beta_corrected": 0.5317},
    "Insurance (Prop/Cas.)": {"n_firms": 57, "de_ratio": 0.1483, "unlevered_beta": 0.4357, "cash_firm_value": 0.0468, "unlevered_beta_corrected": 0.4570},
    "Investments & Asset Management": {"n_firms": 283, "de_ratio": 0.3269, "unlevered_beta": 0.5297, "cash_firm_value": 0.0992, "unlevered_beta_corrected": 0.5881},
    "Machinery": {"n_firms": 105, "de_ratio": 0.1469, "unlevered_beta": 0.8680, "cash_firm_value": 0.0291, "unlevered_beta_corrected": 0.8940},
    "Metals & Mining": {"n_firms": 73, "de_ratio": 0.1098, "unlevered_beta": 0.9636, "cash_firm_value": 0.0463, "unlevered_beta_corrected": 1.0104},
    "Office Equipment & Services": {"n_firms": 14, "de_ratio": 0.4810, "unlevered_beta": 0.9806, "cash_firm_value": 0.0555, "unlevered_beta_corrected": 1.0382},
    "Oil/Gas (Integrated)": {"n_firms": 4, "de_ratio": 0.1385, "unlevered_beta": 0.2712, "cash_firm_value": 0.0244, "unlevered_beta_corrected": 0.2780},
    "Oil/Gas (Production and Exploration)": {"n_firms": 142, "de_ratio": 0.3759, "unlevered_beta": 0.5628, "cash_firm_value": 0.0273, "unlevered_beta_corrected": 0.5785},
    "Oil/Gas Distribution": {"n_firms": 23, "de_ratio": 0.5853, "unlevered_beta": 0.4651, "cash_firm_value": 0.0089, "unlevered_beta_corrected": 0.4693},
    "Oilfield Svcs/Equip.": {"n_firms": 97, "de_ratio": 0.3736, "unlevered_beta": 0.7430, "cash_firm_value": 0.0559, "unlevered_beta_corrected": 0.7871},
    "Packaging & Container": {"n_firms": 19, "de_ratio": 0.5511, "unlevered_beta": 0.7231, "cash_firm_value": 0.0346, "unlevered_beta_corrected": 0.7490},
    "Paper/Forest Products": {"n_firms": 6, "de_ratio": 0.4369, "unlevered_beta": 0.7216, "cash_firm_value": 0.0625, "unlevered_beta_corrected": 0.7697},
    "Power": {"n_firms": 46, "de_ratio": 0.7415, "unlevered_beta": 0.3100, "cash_firm_value": 0.0145, "unlevered_beta_corrected": 0.3146},
    "Precious Metals": {"n_firms": 56, "de_ratio": 0.0728, "unlevered_beta": 0.7932, "cash_firm_value": 0.0453, "unlevered_beta_corrected": 0.8309},
    "Publishing & Newspapers": {"n_firms": 19, "de_ratio": 0.2394, "unlevered_beta": 0.4773, "cash_firm_value": 0.0675, "unlevered_beta_corrected": 0.5119},
    "R.E.I.T.": {"n_firms": 190, "de_ratio": 0.8446, "unlevered_beta": 0.3929, "cash_firm_value": 0.0191, "unlevered_beta_corrected": 0.4005},
    "Real Estate (Development)": {"n_firms": 14, "de_ratio": 1.0183, "unlevered_beta": 0.4783, "cash_firm_value": 0.1521, "unlevered_beta_corrected": 0.5641},
    "Real Estate (General/Diversified)": {"n_firms": 12, "de_ratio": 0.5356, "unlevered_beta": 0.5779, "cash_firm_value": 0.0783, "unlevered_beta_corrected": 0.6270},
    "Real Estate (Operations & Services)": {"n_firms": 54, "de_ratio": 0.2464, "unlevered_beta": 0.8149, "cash_firm_value": 0.0498, "unlevered_beta_corrected": 0.8576},
    "Recreation": {"n_firms": 49, "de_ratio": 0.6299, "unlevered_beta": 0.6951, "cash_firm_value": 0.0562, "unlevered_beta_corrected": 0.7365},
    "Reinsurance": {"n_firms": 1, "de_ratio": 0.4347, "unlevered_beta": 0.4384, "cash_firm_value": 0.2411, "unlevered_beta_corrected": 0.5777},
    "Restaurant/Dining": {"n_firms": 64, "de_ratio": 0.2722, "unlevered_beta": 0.7674, "cash_firm_value": 0.0199, "unlevered_beta_corrected": 0.7830},
    "Retail (Automotive)": {"n_firms": 34, "de_ratio": 0.4536, "unlevered_beta": 0.6984, "cash_firm_value": 0.0208, "unlevered_beta_corrected": 0.7132},
    "Retail (Building Supply)": {"n_firms": 14, "de_ratio": 0.2329, "unlevered_beta": 1.3070, "cash_firm_value": 0.0081, "unlevered_beta_corrected": 1.3177},
    "Retail (Distributors)": {"n_firms": 62, "de_ratio": 0.2824, "unlevered_beta": 0.7827, "cash_firm_value": 0.0236, "unlevered_beta_corrected": 0.8016},
    "Retail (General)": {"n_firms": 23, "de_ratio": 0.0794, "unlevered_beta": 0.7600, "cash_firm_value": 0.0268, "unlevered_beta_corrected": 0.7809},
    "Retail (Grocery and Food)": {"n_firms": 15, "de_ratio": 0.5195, "unlevered_beta": 0.8048, "cash_firm_value": 0.0514, "unlevered_beta_corrected": 0.8484},
    "Retail (REITs)": {"n_firms": 26, "de_ratio": 0.5642, "unlevered_beta": 0.4362, "cash_firm_value": 0.0148, "unlevered_beta_corrected": 0.4427},
    "Retail (Special Lines)": {"n_firms": 94, "de_ratio": 0.1976, "unlevered_beta": 0.9488, "cash_firm_value": 0.0530, "unlevered_beta_corrected": 1.0019},
    "Rubber& Tires": {"n_firms": 3, "de_ratio": 3.5847, "unlevered_beta": 0.1435, "cash_firm_value": 0.0701, "unlevered_beta_corrected": 0.1544},
    "Semiconductor": {"n_firms": 66, "de_ratio": 0.0259, "unlevered_beta": 1.4893, "cash_firm_value": 0.0102, "unlevered_beta_corrected": 1.5046},
    "Semiconductor Equip": {"n_firms": 31, "de_ratio": 0.0486, "unlevered_beta": 1.3481, "cash_firm_value": 0.0313, "unlevered_beta_corrected": 1.3917},
    "Shipbuilding & Marine": {"n_firms": 8, "de_ratio": 0.2255, "unlevered_beta": 0.6440, "cash_firm_value": 0.0254, "unlevered_beta_corrected": 0.6608},
    "Shoe": {"n_firms": 11, "de_ratio": 0.1194, "unlevered_beta": 0.9337, "cash_firm_value": 0.0665, "unlevered_beta_corrected": 1.0002},
    "Software (Entertainment)": {"n_firms": 77, "de_ratio": 0.0204, "unlevered_beta": 1.0128, "cash_firm_value": 0.0078, "unlevered_beta_corrected": 1.0207},
    "Software (Internet)": {"n_firms": 29, "de_ratio": 0.1230, "unlevered_beta": 1.5461, "cash_firm_value": 0.0280, "unlevered_beta_corrected": 1.5905},
    "Software (System & Application)": {"n_firms": 309, "de_ratio": 0.0558, "unlevered_beta": 1.2254, "cash_firm_value": 0.0183, "unlevered_beta_corrected": 1.2482},
    "Steel": {"n_firms": 19, "de_ratio": 0.2351, "unlevered_beta": 0.9035, "cash_firm_value": 0.0438, "unlevered_beta_corrected": 0.9449},
    "Telecom (Wireless)": {"n_firms": 12, "de_ratio": 0.5195, "unlevered_beta": 0.3873, "cash_firm_value": 0.0132, "unlevered_beta_corrected": 0.3924},
    "Telecom. Equipment": {"n_firms": 57, "de_ratio": 0.0922, "unlevered_beta": 0.8635, "cash_firm_value": 0.0268, "unlevered_beta_corrected": 0.8873},
    "Telecom. Services": {"n_firms": 39, "de_ratio": 0.9606, "unlevered_beta": 0.3654, "cash_firm_value": 0.0421, "unlevered_beta_corrected": 0.3815},
    "Tobacco": {"n_firms": 10, "de_ratio": 0.2297, "unlevered_beta": 0.6776, "cash_firm_value": 0.0184, "unlevered_beta_corrected": 0.6903},
    "Transportation": {"n_firms": 19, "de_ratio": 0.3645, "unlevered_beta": 0.6753, "cash_firm_value": 0.0509, "unlevered_beta_corrected": 0.7115},
    "Transportation (Railroads)": {"n_firms": 4, "de_ratio": 0.2779, "unlevered_beta": 0.8069, "cash_firm_value": 0.0083, "unlevered_beta_corrected": 0.8137},
    "Trucking": {"n_firms": 26, "de_ratio": 0.2523, "unlevered_beta": 0.8504, "cash_firm_value": 0.0212, "unlevered_beta_corrected": 0.8689},
    "Utility (General)": {"n_firms": 14, "de_ratio": 0.8148, "unlevered_beta": 0.1486, "cash_firm_value": 0.0033, "unlevered_beta_corrected": 0.1491},
    "Utility (Water)": {"n_firms": 14, "de_ratio": 0.6236, "unlevered_beta": 0.2812, "cash_firm_value": 0.0046, "unlevered_beta_corrected": 0.2825},
}


def get_unlevered_beta(industry: str) -> Optional[float]:
    """Return cash-corrected unlevered beta for an industry, or None if not found."""
    entry = DAMODARAN_BETAS.get(industry)
    return entry["unlevered_beta_corrected"] if entry else None


def compute_bottom_up_beta(
    industry: str,
    market_de: float,
    marginal_tax_rate: float,
) -> Dict:
    """
    Compute bottom-up levered beta using Damodaran's relevering formula.

    Levered Beta = Unlevered Beta × (1 + (1 - t) × D/E)

    Uses the cash-corrected unlevered beta from the industry table
    (Damodaran's recommended pure-play beta).

    Args:
        industry: Damodaran industry name (must exist in DAMODARAN_BETAS)
        market_de: Company's current market debt-to-equity ratio
        marginal_tax_rate: Marginal tax rate (typically 0.21 for US)

    Returns:
        Dict with: levered_beta, unlevered_beta, industry, market_de,
        tax_rate, n_firms

    Raises:
        ValueError: If industry not in DAMODARAN_BETAS
    """
    entry = DAMODARAN_BETAS.get(industry)
    if entry is None:
        raise ValueError(
            f"Industry '{industry}' not found in DAMODARAN_BETAS table. "
            f"Check available industries via list(DAMODARAN_BETAS.keys())."
        )
    unlevered = entry["unlevered_beta_corrected"]
    levered = unlevered * (1 + (1 - marginal_tax_rate) * market_de)
    return {
        "levered_beta": levered,
        "unlevered_beta": unlevered,
        "industry": industry,
        "market_de": market_de,
        "tax_rate": marginal_tax_rate,
        "n_firms": entry["n_firms"],
    }


# Mapping from Alpha Vantage industry strings (Industry field in OVERVIEW)
# to Damodaran industry names. AV uses SEC standard industrial classification
# in uppercase; Damodaran uses his own ~94-category taxonomy. Mismatches are
# resolved by matching the closest Damodaran category (manual mapping).
#
# Keys are normalized to UPPERCASE -- suggest_industry() uppercases its input.
# Values must EXACTLY match keys in DAMODARAN_BETAS (including any typos
# preserved from Damodaran's source -- e.g., "Heathcare Information and Technology").
AV_TO_DAMODARAN_HINT: Dict[str, str] = {
    # Technology
    "SEMICONDUCTORS": "Semiconductor",
    "SEMICONDUCTORS & RELATED DEVICES": "Semiconductor",
    "SERVICES-PREPACKAGED SOFTWARE": "Software (System & Application)",
    "SERVICES-COMPUTER PROGRAMMING, DATA PROCESSING, ETC.": "Software (System & Application)",
    "COMPUTER & OFFICE EQUIPMENT": "Computers/Peripherals",
    "ELECTRONIC COMPUTERS": "Computers/Peripherals",
    "COMMUNICATIONS EQUIPMENT, NEC": "Telecom. Equipment",
    "RADIO & TV BROADCASTING & COMMUNICATIONS EQUIPMENT": "Telecom. Equipment",
    "SERVICES-COMPUTER INTEGRATED SYSTEMS DESIGN": "Information Services",
    "SERVICES-COMPUTER PROCESSING & DATA PREPARATION": "Information Services",
    # Financials
    "STATE COMMERCIAL BANKS": "Bank (Money Center)",
    "NATIONAL COMMERCIAL BANKS": "Bank (Money Center)",
    "SAVINGS INSTITUTIONS, FEDERALLY CHARTERED": "Banks (Regional)",
    "SECURITY BROKERS, DEALERS & FLOTATION COMPANIES": "Investments & Asset Management",
    "FIRE, MARINE & CASUALTY INSURANCE": "Insurance (Prop/Cas.)",
    "LIFE INSURANCE": "Insurance (Life)",
    # Healthcare
    "PHARMACEUTICAL PREPARATIONS": "Drugs (Pharmaceutical)",
    "BIOLOGICAL PRODUCTS, (NO DIAGNOSTIC SUBSTANCES)": "Drugs (Biotechnology)",
    "ELECTROMEDICAL & ELECTROTHERAPEUTIC APPARATUS": "Healthcare Products",
    "SERVICES-HEALTH SERVICES": "Healthcare Support Services",
    # Energy
    "CRUDE PETROLEUM & NATURAL GAS": "Oil/Gas (Production and Exploration)",
    "PETROLEUM REFINING": "Oil/Gas (Integrated)",
    "NATURAL GAS DISTRIBUTION": "Oil/Gas Distribution",
    # Consumer
    "RETAIL-VARIETY STORES": "Retail (General)",
    "RETAIL-DEPARTMENT STORES": "Retail (General)",
    "RETAIL-EATING PLACES": "Restaurant/Dining",
    "BEVERAGES": "Beverage (Soft)",
    # Industrial
    "MOTOR VEHICLES & PASSENGER CAR BODIES": "Auto & Truck",
    "AIRCRAFT": "Aerospace/Defense",
    "GUIDED MISSILES & SPACE VEHICLES & PARTS": "Aerospace/Defense",
    # Real Estate
    "REAL ESTATE INVESTMENT TRUSTS": "R.E.I.T.",
    # Media
    "SERVICES-MOTION PICTURE & VIDEO TAPE PRODUCTION": "Entertainment",
    "TELEVISION BROADCASTING STATIONS": "Broadcasting",
    "CABLE & OTHER PAY TELEVISION SERVICES": "Cable TV",
    "SERVICES-ADVERTISING": "Advertising",
}


def suggest_industry(av_industry: Optional[str]) -> Optional[str]:
    """
    Suggest a Damodaran industry name from an Alpha Vantage industry string.

    Returns the Damodaran name if the AV string is in our mapping, or None
    if no good match exists. The calibrate skill should always confirm with
    the user before using the suggestion.
    """
    if not av_industry:
        return None
    return AV_TO_DAMODARAN_HINT.get(av_industry.strip().upper())


# Our own sector grouping for the calibrate skill's industry picker.
# Damodaran's table doesn't have sector groupings -- we define them.
# Every industry in DAMODARAN_BETAS must appear in exactly one sector.
# Industry names must match DAMODARAN_BETAS keys exactly (including the
# source-preserved typo "Heathcare Information and Technology" and the
# unspaced "Rubber& Tires").
DAMODARAN_SECTORS: Dict[str, list] = {
    "Technology": [
        "Computer Services",
        "Computers/Peripherals",
        "Electronics (Consumer & Office)",
        "Electronics (General)",
        "Information Services",
        "Semiconductor",
        "Semiconductor Equip",
        "Software (Entertainment)",
        "Software (Internet)",
        "Software (System & Application)",
    ],
    "Healthcare": [
        "Drugs (Biotechnology)",
        "Drugs (Pharmaceutical)",
        "Healthcare Products",
        "Healthcare Support Services",
        "Heathcare Information and Technology",  # Damodaran typo preserved
        "Hospitals/Healthcare Facilities",
    ],
    "Financials": [
        "Bank (Money Center)",
        "Banks (Regional)",
        "Brokerage & Investment Banking",
        "Financial Svcs. (Non-bank & Insurance)",
        "Insurance (General)",
        "Insurance (Life)",
        "Insurance (Prop/Cas.)",
        "Investments & Asset Management",
        "Reinsurance",
    ],
    "Energy": [
        "Coal & Related Energy",
        "Green & Renewable Energy",
        "Oil/Gas (Integrated)",
        "Oil/Gas (Production and Exploration)",
        "Oil/Gas Distribution",
        "Oilfield Svcs/Equip.",
        "Power",
    ],
    "Materials": [
        "Building Materials",
        "Chemical (Basic)",
        "Chemical (Diversified)",
        "Chemical (Specialty)",
        "Metals & Mining",
        "Paper/Forest Products",
        "Precious Metals",
        "Rubber& Tires",  # Damodaran spacing preserved
        "Steel",
    ],
    "Industrials": [
        "Aerospace/Defense",
        "Business & Consumer Services",
        "Construction Supplies",
        "Diversified",
        "Electrical Equipment",
        "Engineering/Construction",
        "Environmental & Waste Services",
        "Farming/Agriculture",
        "Machinery",
        "Office Equipment & Services",
        "Packaging & Container",
        "Shipbuilding & Marine",
    ],
    "Consumer Discretionary": [
        "Apparel",
        "Auto & Truck",
        "Auto Parts",
        "Education",
        "Entertainment",
        "Furn/Home Furnishings",
        "Homebuilding",
        "Hotel/Gaming",
        "Recreation",
        "Restaurant/Dining",
        "Retail (Automotive)",
        "Retail (Building Supply)",
        "Retail (Distributors)",
        "Retail (General)",
        "Retail (Special Lines)",
        "Shoe",
    ],
    "Consumer Staples": [
        "Beverage (Alcoholic)",
        "Beverage (Soft)",
        "Food Processing",
        "Food Wholesalers",
        "Household Products",
        "Retail (Grocery and Food)",
        "Tobacco",
    ],
    "Communication Services": [
        "Advertising",
        "Broadcasting",
        "Cable TV",
        "Publishing & Newspapers",
        "Telecom (Wireless)",
        "Telecom. Equipment",
        "Telecom. Services",
    ],
    "Utilities": [
        "Utility (General)",
        "Utility (Water)",
    ],
    "Real Estate": [
        "R.E.I.T.",
        "Real Estate (Development)",
        "Real Estate (General/Diversified)",
        "Real Estate (Operations & Services)",
        "Retail (REITs)",
    ],
    "Transportation": [
        "Air Transport",
        "Transportation",
        "Transportation (Railroads)",
        "Trucking",
    ],
}

